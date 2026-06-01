"""本地 data 目录读取实现。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

from ..schemas import CommentItem, FriendOption, ShuoshuoItem, build_comment_item, build_shuoshuo_item


class LocalSource:
    """本地结构化文件数据源。

    仅读取真实存在的 `shuoshuo.sqlite` 或 `shuoshuo.jsonl`，不推断抓取断点。
    """

    def __init__(self, data_dir: str) -> None:
        self._root = Path(data_dir)

    def list_friends(self) -> List[FriendOption]:
        """列出所有具备本地结构化文件的好友 QQ。"""
        out: List[FriendOption] = []
        if not self._root.exists():
            return out
        for child in sorted(self._root.iterdir(), key=lambda p: p.name):
            if not child.is_dir() or not child.name.isdigit():
                continue
            file_info = self._detect_data_file(child)
            if not file_info:
                continue
            file_kind, file_path = file_info
            count = self._count_records(file_kind, file_path)
            out.append(FriendOption(target_qq=int(child.name), count=count, source="local"))
        return out

    def list_shuoshuo(
        self,
        target_qq: int,
        page: int,
        page_size: int,
        sort: str,
        start_ts: int | None,
        end_ts: int | None,
    ) -> Tuple[List[ShuoshuoItem], int]:
        """查询本地说说分页结果。"""
        records = self._load_records(target_qq)
        filtered = self._filter_records(records, start_ts, end_ts)
        ordered = sorted(filtered, key=lambda item: int(item.get("created_time") or 0), reverse=sort == "desc")
        total = len(ordered)
        chunk = ordered[(page - 1) * page_size : page * page_size]
        return [build_shuoshuo_item(item) for item in chunk], total

    def list_comments(
        self,
        target_qq: int,
        tid: str,
        page: int,
        page_size: int,
    ) -> Tuple[List[CommentItem], int]:
        """查询某条本地说说下的评论分页结果。"""
        record = self._find_record(target_qq, tid)
        comments = list(record.get("comments") or []) if record else []
        comments.sort(key=lambda item: int(item.get("created_time") or 0))
        total = len(comments)
        chunk = comments[(page - 1) * page_size : page * page_size]
        return [build_comment_item(item) for item in chunk], total

    def _find_record(self, target_qq: int, tid: str) -> Dict[str, object] | None:
        """查找单条说说原始记录。"""
        for item in self._load_records(target_qq):
            if str(item.get("tid") or "") == tid:
                return item
        return None

    def _load_records(self, target_qq: int) -> List[Dict[str, object]]:
        """读取某个好友的全部说说结构化记录。"""
        target_dir = self._root / str(target_qq)
        file_info = self._detect_data_file(target_dir)
        if not file_info:
            return []
        file_kind, file_path = file_info
        if file_kind == "sqlite":
            return self._load_sqlite(file_path)
        return self._load_jsonl(file_path)

    def _detect_data_file(self, target_dir: Path) -> Tuple[str, Path] | None:
        """按固定优先级探测本地结构化文件。"""
        sqlite_path = target_dir / "shuoshuo.sqlite"
        if sqlite_path.exists():
            return ("sqlite", sqlite_path)
        jsonl_path = target_dir / "shuoshuo.jsonl"
        if jsonl_path.exists():
            return ("jsonl", jsonl_path)
        return None

    def _count_records(self, file_kind: str, file_path: Path) -> int:
        """统计本地结构化文件记录数。"""
        if file_kind == "sqlite":
            conn = sqlite3.connect(file_path)
            try:
                row = conn.execute("SELECT COUNT(*) FROM shuoshuo").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        count = 0
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def _load_sqlite(self, file_path: Path) -> List[Dict[str, object]]:
        """从本地 SQLite 读取全部 JSON 数据。"""
        conn = sqlite3.connect(file_path)
        try:
            rows = conn.execute("SELECT data FROM shuoshuo").fetchall()
            return [json.loads(row[0]) for row in rows]
        finally:
            conn.close()

    def _load_jsonl(self, file_path: Path) -> List[Dict[str, object]]:
        """从 JSONL 读取全部记录。"""
        out: List[Dict[str, object]] = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out

    @staticmethod
    def _filter_records(
        records: List[Dict[str, object]],
        start_ts: int | None,
        end_ts: int | None,
    ) -> List[Dict[str, object]]:
        """按时间区间过滤本地记录。"""
        out: List[Dict[str, object]] = []
        for item in records:
            created_time = int(item.get("created_time") or 0)
            if start_ts is not None and created_time < start_ts:
                continue
            if end_ts is not None and created_time > end_ts:
                continue
            out.append(item)
        return out
