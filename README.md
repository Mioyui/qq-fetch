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
- 依赖:`httpx`(以及 Python < 3.11 时的 `tomli`)

## 安装

```bash
# 建议在虚拟环境中
pip install -e .            # 安装为可编辑包,提供 qqfetch 命令
# 或仅安装运行依赖
pip install -r requirements.txt
```

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
- `[storage] storage_format`:`jsonl`(默认,可读) 或 `sqlite`

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

## 无痕验证

1. **抓包**(mitmproxy / Fiddler):运行抓取,确认**没有任何对 `user.qzone.qq.com/{目标QQ}` 主页的请求**,只有 `emotion_cgi_msglist_v6` 数据接口和图片 CDN。
2. **访客对比**:用第二个能查看目标"最近访客"的账号,在抓取前后对比访客列表,确认抓取账号未出现。
3. **代码层兜底**:`QzoneClient._assert_traceless` 会拦截任何主页 URL(见 `tests/test_client.py::test_traceless_blocks_homepage`)。

## 运行测试

```bash
pip install -e ".[dev]"
pytest
```

单元测试覆盖:hash33/g_tk 签名(交叉验证)、ptuiCB 回调解析、说说/图片解析、断点续传、分页去重、失效与风控分流、限速重试、无痕断言等。涉及真实 QQ 接口的部分(扫码、实际抓取)需用真实账号通过探测脚本与冒烟测试验证。

## 接口时效性

`ptlogin2` 扫码、`g_tk` 算法多年稳定;`emotion_cgi_msglist_v6` 的参数/字段可能调整。若抓取异常,优先重跑探测脚本对照最新返回,并校正 `parser.py` / `image_urls.py` 的字段兜底与 `client.py` 的接口 URL。

## 合规与免责

- 仅抓取你作为好友**本就有权查看**的内容;数据仅供个人备份/留念,**不传播、不商用**。
- 自动化抓取可能触及平台服务条款,请**自行评估风险**并合理限速,避免账号受限。
- 本工具仅供学习与个人使用,使用者需对自身行为负责。
