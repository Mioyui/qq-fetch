# qq-fetch —— QQ 空间说说无痕抓取工具

通过**扫码登录**获取登录态,抓取**指定好友**的 QQ 空间说说(正文、时间、点赞/评论、**图片原图**)并本地保存。核心特性是**无痕**——抓取不会在对方的"最近访客"留下记录。

## 无痕原理(最关键)

QQ 空间的"最近访客"是由**访问空间主页**(`user.qzone.qq.com/{QQ}`)时前端的上报行为触发的;而**直接调用底层数据接口**(`emotion_cgi_msglist_v6`)拉取 JSON **通常不会写入对方访客记录**。

因此本工具的核心约束是:**全程只请求数据接口,绝不访问目标空间主页**。这一约束在代码层通过 `QzoneClient` 的 URL 白名单断言强制保证——任何指向目标主页的请求都会立即抛 `TracelessViolationError`。

> ⚠️ "无痕"应理解为"目前/通常无痕",非腾讯官方保证。请在使用前用 [无痕验证](#无痕验证) 自行确认。

## 特性

- 🔐 扫码登录,登录态本地持久化,**免重复扫码**;失效自动重新登录
- 📄 分页抓取全部说说,**断点续传**,中断可续、重复运行不重抓
- 🖼️ 下载图片原图,**跨运行去重**,失败记录不阻断
- 🚦 请求随机限速 + 失败指数退避,降低风控概率
- 🧩 多字段名容错解析 + 保留原始 JSON,接口微调也能事后补救
- ✅ 纯函数与核心逻辑均有单元测试

## 环境要求

- Python ≥ 3.9
- 依赖:`httpx`、`psycopg`(PostgreSQL 入库时使用),以及 Python < 3.11 时的 `tomli`

## 安装

```bash
# 建议在虚拟环境中
pip install -e .            # 安装为可编辑包,提供 qqfetch 命令
# 或仅安装运行依赖
pip install -r requirements.txt
```

`requirements.txt` 只覆盖基础抓取依赖。  
如果要启用 PostgreSQL 入库,建议直接执行 `pip install -e .`,或额外安装 `psycopg>=3.2`,并确认数据库网络连通。

开发(含测试工具):

```bash
pip install -e ".[dev]"     # httpx + pytest + respx + ruff
```

## 快速开始

### 第 0 步(强烈建议):用探测脚本校准接口

QQ 接口参数/字段会随时间变动。首次使用前,先运行探测脚本用**你自己的真实账号**实测,确认接口现状并校正解析字段:

```bash
python scripts/probe_login.py        # 扫码,产出 scripts/probe_cookies.json
python scripts/probe_msglist.py      # 抓自己的说说,产出 scripts/msglist_raw.json
```

`probe_msglist.py` 会打印真实返回的字段名。若与 `qqfetch/qzone/parser.py`、`image_urls.py` 中的兜底键不一致,据实校正;并可把脱敏后的 `msglist_raw.json` 另存为 `tests/fixtures/msglist_sample.json` 驱动单测。

### 第 1 步:配置

```bash
cp config.example.toml config.toml
# 编辑 config.toml,至少设置 [target] qq = 目标好友QQ
```

如需直接入库 PostgreSQL,还需要在 `[storage]` 节设置:

```toml
[storage]
storage_format = "postgres"
postgres_dsn = "postgresql://user:password@127.0.0.1:5432/qqfetch"
postgres_schema = "public"
postgres_auto_init = true
```

### 第 2 步:扫码登录

```bash
qqfetch login          # 或: python -m qqfetch login
```

弹出二维码(默认保存 PNG 并用系统默认程序打开),用手机 QQ 扫码确认。登录态保存在 `data/session.json`。

### 第 3 步:抓取

```bash
qqfetch fetch --target 123456789          # 抓取指定好友
qqfetch fetch --target 123456789 --max 5  # 仅抓 5 条(冒烟测试)
qqfetch fetch --target 123456789 --no-images   # 不下载图片
```

如果 `storage_format = "postgres"` 且 `postgres_auto_init = true`,首次抓取前会自动执行仓库内置建表 SQL:`sql/postgres_schema.sql`。

## 命令与参数

| 命令 | 说明 |
|------|------|
| `qqfetch login` | 扫码登录并保存登录态 |
| `qqfetch fetch` | 抓取指定好友的说说 |

`fetch` 参数(覆盖 config.toml):

| 参数 | 说明 |
|------|------|
| `--target <QQ>` | 目标好友 QQ |
| `--max <N>` | 最多抓取条数(0=全部) |
| `--no-images` | 不下载图片 |
| `--reset-login` | 忽略已保存登录态,强制重新扫码 |
| `--reset` | 清空断点,重新全量抓取 |
| `--config <path>` | 指定配置文件路径 |

## 配置说明

见 `config.example.toml`,各项均有中文注释。要点:

- `[network] delay_min/delay_max`:请求间随机延时(秒),**调大更安全**
- `[fetch] image_concurrency`:图片并发,**调高更易触发风控**,默认 1
- `[storage] storage_format`:`jsonl`(默认,可读)、`sqlite` 或 `postgres`
- `[storage] postgres_dsn`:PostgreSQL 连接串;当 `storage_format = "postgres"` 时必填
- `[storage] postgres_schema`:建表/查询使用的 schema,默认 `public`
- `[storage] postgres_auto_init`:是否在抓取前自动执行 `sql/postgres_schema.sql`,默认 `true`

## 本地浏览页

项目现在内置了一个 Web 浏览页,用于按好友 QQ 浏览已经抓取到的说说数据。

### 启动方式

```bash
python -m qqfetch web
```

可选参数:

```bash
python -m qqfetch web --host 127.0.0.1 --port 8000
```

启动后默认访问:

```text
http://127.0.0.1:8000/
```

### 页面功能

- 选择数据源:本地 `data/` 或 PostgreSQL
- 选择好友 QQ
- 说说主列表分页
- 每条说说内评论独立分页
- 按发布时间升序/降序切换
- 起止日期筛选
- 快捷时间区间:`全部`、`近7天`、`近30天`、`近90天`、`近1年`

页面视觉参考 QQ 空间,但做了更精简的布局:

- 左侧为筛选与好友选择
- 右侧为说说列表与分页器
- 图片以网格展示
- 评论区按卡片展开,不刷新整页

### 两种数据源

#### 1. 本地数据源 `local`

本地源只读取当前真实存在的结构化文件,查找顺序固定为:

1. `data/<QQ>/shuoshuo.sqlite`
2. `data/<QQ>/shuoshuo.jsonl`

如果目标目录下只有 `checkpoint.json` 和 `images/`,而没有 `shuoshuo.sqlite` 或 `shuoshuo.jsonl`,则该 QQ 不会出现在本地源的好友列表里。

这意味着:

- 如果抓取时使用的是 `storage_format = "jsonl"` 或 `storage_format = "sqlite"`,通常可以直接从本地源浏览
- 如果抓取时使用的是 `storage_format = "postgres"`,当前实现默认不会额外落一份本地结构化说说文件,因此本地源可能为空

#### 2. 数据库数据源 `postgres`

数据库源直接读取 PostgreSQL 中的三张表:

- `qqfetch_shuoshuo`
- `qqfetch_comment`
- `qqfetch_picture`

它依赖当前配置文件中的:

- `storage.postgres_dsn`
- `storage.postgres_schema`

数据库源只支持 PostgreSQL,当前不支持把 SQLite 当作 Web 数据源直接查询。

### 已知限制

- 浏览页只做只读展示,不支持重新抓取、编辑或删除
- 时间筛选和升降序只作用于说说列表,不单独作用于评论
- 好友列表默认以 QQ 号展示,不额外解析昵称
- 本地源不会自动把 PostgreSQL 中的数据补回 `data/` 目录

## PostgreSQL 入库说明

`storage_format = "postgres"` 时,抓取结果会按“当前快照”写入 PostgreSQL:

- 说说主表使用 `(target_qq, tid)` 作为主键,重复抓取同一条说说时执行 UPSERT
- 评论和图片按 `(target_qq, tid)` 先删除旧快照,再写入新快照
- 主表保留结构化字段,同时保存 `raw JSONB`,方便后续补字段或排查接口变化

程序默认提供并自动执行建表 SQL,也可以把 `postgres_auto_init = false` 改为手工建表。

手工建表示例:

```bash
# 先创建数据库(仅首次)
createdb qqfetch

# 再导入表结构
psql "postgresql://user:password@127.0.0.1:5432/qqfetch" -f sql/postgres_schema.sql
```

内置表结构如下:

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `qqfetch_shuoshuo` | 说说主表 | `target_qq`,`tid`,`content`,`created_time`,`like_count`,`comment_count`,`raw`,`first_seen_at`,`last_seen_at` |
| `qqfetch_comment` | 评论快照表 | `target_qq`,`tid`,`comment_key`,`comment_id`,`content`,`created_time`,`author_uin`,`author_name` |
| `qqfetch_picture` | 图片快照表 | `target_qq`,`tid`,`pic_id`,`url`,`width`,`height`,`sort_index` |

其中评论唯一键规则为:

- 优先使用接口返回的 `comment_id`
- 若 `comment_id` 为空,回退为 `sha1(f"{target_qq}:{tid}:{author_uin}:{created_time}:{content}")[:40]`

## 数据存储结构

```
data/
├── session.json                 # 登录态(默认)
└── <目标QQ>/
    ├── shuoshuo.jsonl           # 说说数据,每行一条 JSON
    ├── checkpoint.json          # 断点(pos + 已抓 tid)
    └── images/
        ├── <tid>_<序号>.jpg     # 图片原图
        ├── .index               # 已下载去重索引
        └── failed_images.log    # 下载失败记录
```

当 `storage_format = "sqlite"` 时,目标目录中的主数据文件为 `shuoshuo.sqlite`。

当 `storage_format = "postgres"` 时:

- 目标目录仍会保存 `checkpoint.json` 和 `images/`
- 说说、评论、图片元数据写入 PostgreSQL
- 不会在本地额外生成可查询的主数据文件
- 如需切换目标库,只需修改 `[storage]` 下的 PostgreSQL 连接配置

## 无痕验证

1. **抓包**(mitmproxy / Fiddler):运行抓取,确认**没有任何对 `user.qzone.qq.com/{目标QQ}` 主页的请求**,只有 `emotion_cgi_msglist_v6` 数据接口和图片 CDN。
2. **访客对比**:用第二个能查看目标"最近访客"的账号,在抓取前后对比访客列表,确认抓取账号未出现。
3. **代码层兜底**:`QzoneClient._assert_traceless` 会拦截任何主页 URL(见 `tests/test_client.py::test_traceless_blocks_homepage`)。

## 运行测试

```bash
pip install -e ".[dev]"
pytest
```

如需执行 PostgreSQL 集成测试,额外提供测试库连接串:

```bash
# PowerShell
$env:QQFETCH_TEST_POSTGRES_DSN="postgresql://user:password@127.0.0.1:5432/qqfetch_test"
pytest tests/test_repository_postgres.py -q
```

浏览页相关测试:

```bash
pytest tests/test_web_local_source.py tests/test_web_app.py -q
```

如需执行浏览页的 PostgreSQL 数据源测试:

```bash
pytest tests/test_web_postgres_source.py -q
```

单元测试覆盖:hash33/g_tk 签名(交叉验证)、ptuiCB 回调解析、说说/图片解析、断点续传、分页去重、失效与风控分流、限速重试、无痕断言等。涉及真实 QQ 接口的部分(扫码、实际抓取)需用真实账号通过探测脚本与冒烟测试验证。

## 接口时效性

`ptlogin2` 扫码、`g_tk` 算法多年稳定;`emotion_cgi_msglist_v6` 的参数/字段可能调整。若抓取异常,优先重跑探测脚本对照最新返回,并校正 `parser.py` / `image_urls.py` 的字段兜底与 `client.py` 的接口 URL。

## 合规与免责

- 仅抓取你作为好友**本就有权查看**的内容;数据仅供个人备份/留念,**不传播、不商用**。
- 自动化抓取可能触及平台服务条款,请**自行评估风险**并合理限速,避免账号受限。
- 本工具仅供学习与个人使用,使用者需对自身行为负责。
