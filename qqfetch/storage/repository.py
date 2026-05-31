"""说说落盘:JSONL(默认,可读易增量)与 SQLite 两种实现,均按 tid 去重。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator, Protocol, Set

from ..logging_setup import get_logger
from ..models import Shuoshuo

_log = get_logger(__name__)


class Repository(Protocol):
    """落盘仓库接口。"""

    def exists(self, tid: str) -> bool: ...
    def append(self, sh: Shuoshuo) -> None: ...
    def count(self) -> int: ...
    def close(self) -> None: ...


class JsonlRepository:
    """每行一条说说的 JSONL 仓库;启动时加载已存 tid 索引以支持去重。"""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: Set[str] = set()
        self._load_index()

    def _load_index(self) -> None:
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
        return tid in self._seen

    def append(self, sh: Shuoshuo) -> None:
        if sh.tid in self._seen:
            return
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sh.to_dict(), ensure_ascii=False) + "\n")
        self._seen.add(sh.tid)

    def count(self) -> int:
        return len(self._seen)

    def close(self) -> None:
        pass


class SqliteRepository:
    """SQLite 仓库:tid 主键去重,完整 JSON 存于 data 列。"""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS shuoshuo ("
            "tid TEXT PRIMARY KEY, created_time INTEGER, content TEXT, data TEXT)"
        )
        self._conn.commit()

    def exists(self, tid: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM shuoshuo WHERE tid=?", (tid,))
        return cur.fetchone() is not None

    def append(self, sh: Shuoshuo) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO shuoshuo(tid, created_time, content, data) VALUES(?,?,?,?)",
            (sh.tid, sh.created_time, sh.content, json.dumps(sh.to_dict(), ensure_ascii=False)),
        )
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM shuoshuo").fetchone()[0])

    def all(self) -> Iterator[dict]:
        for (data,) in self._conn.execute("SELECT data FROM shuoshuo ORDER BY created_time DESC"):
            yield json.loads(data)

    def close(self) -> None:
        self._conn.close()


def make_repository(fmt: str, path: str) -> Repository:
    """按配置创建仓库实现。"""
    if fmt == "sqlite":
        return SqliteRepository(path)
    return JsonlRepository(path)
