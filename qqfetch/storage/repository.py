"""说说落盘与入库仓储。

统一抽象为“保存当前快照”语义:
- JSONL / SQLite: 仅首次写入返回 True，已存在则跳过。
- PostgreSQL: 主表 UPSERT，子表按最新快照重建，首次入库返回 True。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict, Iterator, Optional, Protocol, Set

from ..errors import ConfigError
from ..logging_setup import get_logger
from ..models import Comment, Shuoshuo

_log = get_logger(__name__)
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Repository(Protocol):
    """仓储接口。

    save() 返回值表示当前说说是否为首次入库，便于抓取层继续沿用
    “仅对新增内容做计数/下载图片”的既有行为。
    """

    def save(self, sh: Shuoshuo) -> bool: ...
    def count(self) -> int: ...
    def close(self) -> None: ...


class JsonlRepository:
    """每行一条说说的 JSONL 仓储。"""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: Set[str] = set()
        self._load_index()

    def _load_index(self) -> None:
        """启动时重建已存 tid 索引，用于去重。"""
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._seen.add(str(json.loads(line)["tid"]))
                except (json.JSONDecodeError, KeyError):
                    continue

    def exists(self, tid: str) -> bool:
        """判断 tid 是否已存在。"""
        return tid in self._seen

    def append(self, sh: Shuoshuo) -> None:
        """兼容旧接口:仅在不存在时追加写入。"""
        self.save(sh)

    def save(self, sh: Shuoshuo) -> bool:
        """保存当前说说;已存在时直接跳过。"""
        if sh.tid in self._seen:
            return False
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sh.to_dict(), ensure_ascii=False) + "\n")
        self._seen.add(sh.tid)
        return True

    def count(self) -> int:
        return len(self._seen)

    def close(self) -> None:
        pass


class SqliteRepository:
    """本地 SQLite 仓储。

    这里保持原有轻量行为:仅首次写入说说主记录，完整结构仍放在 data 列。
    """

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS shuoshuo ("
            "tid TEXT PRIMARY KEY, created_time INTEGER, content TEXT, data TEXT)"
        )
        self._conn.commit()

    def exists(self, tid: str) -> bool:
        """判断 tid 是否已存在。"""
        cur = self._conn.execute("SELECT 1 FROM shuoshuo WHERE tid=?", (tid,))
        return cur.fetchone() is not None

    def append(self, sh: Shuoshuo) -> None:
        """兼容旧接口:仅在不存在时写入。"""
        self.save(sh)

    def save(self, sh: Shuoshuo) -> bool:
        """保存当前说说;已存在时直接跳过。"""
        before = self._conn.total_changes
        self._conn.execute(
            "INSERT OR IGNORE INTO shuoshuo(tid, created_time, content, data) VALUES(?,?,?,?)",
            (sh.tid, sh.created_time, sh.content, json.dumps(sh.to_dict(), ensure_ascii=False)),
        )
        self._conn.commit()
        return self._conn.total_changes > before

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM shuoshuo").fetchone()[0])

    def all(self) -> Iterator[dict]:
        """按时间倒序读取全部原始记录。"""
        for (data,) in self._conn.execute("SELECT data FROM shuoshuo ORDER BY created_time DESC"):
            yield json.loads(data)

    def close(self) -> None:
        self._conn.close()


class PostgresRepository:
    """PostgreSQL 仓储。

    说说主表保存结构化字段与 raw JSONB，评论和图片表始终保持当前快照。
    """

    def __init__(
        self,
        dsn: str,
        *,
        target_qq: int,
        schema: str = "public",
        auto_init: bool = True,
    ) -> None:
        if target_qq <= 0:
            raise ConfigError("PostgreSQL 入库要求 target_qq 为正整数")
        if not dsn.strip():
            raise ConfigError("storage_format=postgres 时必须配置 storage.postgres_dsn")
        if not _SCHEMA_RE.fullmatch(schema):
            raise ConfigError("storage.postgres_schema 仅允许字母、数字、下划线，且不能以数字开头")

        psycopg = _load_psycopg()
        self._psycopg = psycopg
        self._sql = psycopg.sql
        self._jsonb = psycopg.types.json.Jsonb
        self._target_qq = target_qq
        self._schema = schema
        try:
            # 开启 autocommit,让 connection.transaction() 真正作为顶层事务提交。
            # 否则在 psycopg 默认事务模式下,这里会变成保存点,连接关闭时整批写入会被回滚。
            self._conn = psycopg.connect(dsn, autocommit=True)
        except psycopg.OperationalError as exc:
            raise _postgres_connect_error(dsn, exc) from exc
        if auto_init:
            self._init_schema()

    def _table(self, name: str):
        """生成带 schema 的安全表名。"""
        return self._sql.Identifier(self._schema, name)

    def _init_schema(self) -> None:
        """执行仓库内置建表 SQL。"""
        sql_path = Path(__file__).resolve().parents[2] / "sql" / "postgres_schema.sql"
        text = sql_path.read_text(encoding="utf-8")
        rendered = text.replace("__QQFETCH_SCHEMA__", f'"{self._schema}"')
        with self._conn.transaction():
            with self._conn.cursor() as cur:
                cur.execute(rendered)

    def exists(self, tid: str) -> bool:
        """判断当前目标 QQ 下的 tid 是否已存在。"""
        stmt = self._sql.SQL("SELECT 1 FROM {} WHERE target_qq=%s AND tid=%s").format(
            self._table("qqfetch_shuoshuo")
        )
        with self._conn.cursor() as cur:
            cur.execute(stmt, (self._target_qq, tid))
            return cur.fetchone() is not None

    def save(self, sh: Shuoshuo) -> bool:
        """保存一条说说快照。

        主表做 UPSERT；评论和图片按当前快照整条替换，避免脏子记录残留。
        """
        is_new = not self.exists(sh.tid)
        with self._conn.transaction():
            self._upsert_shuoshuo(sh)
            self._replace_comments(sh)
            self._replace_pictures(sh)
        return is_new

    def _upsert_shuoshuo(self, sh: Shuoshuo) -> None:
        """UPSERT 说说主表。"""
        stmt = self._sql.SQL(
            """
            INSERT INTO {} (
                target_qq, tid, content, created_time, like_count, comment_count, raw
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (target_qq, tid) DO UPDATE SET
                content = EXCLUDED.content,
                created_time = EXCLUDED.created_time,
                like_count = EXCLUDED.like_count,
                comment_count = EXCLUDED.comment_count,
                raw = EXCLUDED.raw,
                last_seen_at = NOW()
            """
        ).format(self._table("qqfetch_shuoshuo"))
        raw_json = self._jsonb(sh.raw or {})
        with self._conn.cursor() as cur:
            cur.execute(
                stmt,
                (
                    self._target_qq,
                    sh.tid,
                    sh.content,
                    sh.created_time,
                    sh.like_count,
                    sh.comment_count,
                    raw_json,
                ),
            )

    def _replace_comments(self, sh: Shuoshuo) -> None:
        """用最新快照重建评论子表。"""
        delete_stmt = self._sql.SQL("DELETE FROM {} WHERE target_qq=%s AND tid=%s").format(
            self._table("qqfetch_comment")
        )
        insert_stmt = self._sql.SQL(
            """
            INSERT INTO {} (
                target_qq, tid, comment_key, comment_id, content, created_time, author_uin, author_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
        ).format(self._table("qqfetch_comment"))
        with self._conn.cursor() as cur:
            cur.execute(delete_stmt, (self._target_qq, sh.tid))
            for c in sh.comments:
                cur.execute(
                    insert_stmt,
                    (
                        self._target_qq,
                        sh.tid,
                        _comment_key(self._target_qq, sh.tid, c),
                        c.comment_id,
                        c.content,
                        c.created_time,
                        c.author_uin,
                        c.author_name,
                    ),
                )

    def _replace_pictures(self, sh: Shuoshuo) -> None:
        """用最新快照重建图片子表。"""
        delete_stmt = self._sql.SQL("DELETE FROM {} WHERE target_qq=%s AND tid=%s").format(
            self._table("qqfetch_picture")
        )
        insert_stmt = self._sql.SQL(
            """
            INSERT INTO {} (
                target_qq, tid, pic_id, url, width, height, sort_index
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
        ).format(self._table("qqfetch_picture"))
        with self._conn.cursor() as cur:
            cur.execute(delete_stmt, (self._target_qq, sh.tid))
            for index, pic in enumerate(sh.pictures):
                cur.execute(
                    insert_stmt,
                    (
                        self._target_qq,
                        sh.tid,
                        pic.pic_id,
                        pic.url,
                        pic.width,
                        pic.height,
                        index,
                    ),
                )

    def count(self) -> int:
        stmt = self._sql.SQL("SELECT COUNT(*) FROM {} WHERE target_qq=%s").format(
            self._table("qqfetch_shuoshuo")
        )
        with self._conn.cursor() as cur:
            cur.execute(stmt, (self._target_qq,))
            return int(cur.fetchone()[0])

    def close(self) -> None:
        self._conn.close()


def _load_psycopg():
    """按需导入 psycopg，避免非 PostgreSQL 用户被强依赖阻塞。"""
    try:
        return importlib.import_module("psycopg")
    except ModuleNotFoundError as exc:
        raise ConfigError("storage_format=postgres 需要安装 psycopg>=3.2") from exc


def _postgres_connect_error(dsn: str, exc: Exception) -> ConfigError:
    """把 psycopg 的底层连接异常转成更可读的配置错误。"""
    parsed = urlparse(dsn)
    host = parsed.hostname or "unknown"
    port = parsed.port or 5432
    dbname = parsed.path.lstrip("/") or "(未指定数据库)"
    return ConfigError(
        "无法连接 PostgreSQL。"
        f"当前目标: host={host} port={port} db={dbname}。"
        "请确认数据库已创建、账号密码正确、端口可访问；"
        "注意 `sql/postgres_schema.sql` 只负责建表，不会自动创建数据库。"
    )


def _comment_key(target_qq: int, tid: str, comment: Comment) -> str:
    """生成评论唯一键。

    优先使用 comment_id；若接口未给出稳定 ID，则回退为内容指纹。
    """
    if comment.comment_id:
        return comment.comment_id
    seed = f"{target_qq}:{tid}:{comment.author_uin}:{comment.created_time}:{comment.content}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:40]


def make_repository(
    fmt: str,
    path: str,
    *,
    target_qq: int = 0,
    postgres_dsn: str = "",
    postgres_schema: str = "public",
    postgres_auto_init: bool = True,
) -> Repository:
    """按配置创建仓储实现。"""
    if fmt == "sqlite":
        return SqliteRepository(path)
    if fmt == "postgres":
        return PostgresRepository(
            postgres_dsn,
            target_qq=target_qq,
            schema=postgres_schema,
            auto_init=postgres_auto_init,
        )
    return JsonlRepository(path)
