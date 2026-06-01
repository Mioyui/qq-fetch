"""PostgreSQL 只读查询实现。"""

from __future__ import annotations

import importlib
import re
from typing import Dict, List, Sequence, Tuple

from ...errors import ConfigError
from ..schemas import CommentItem, FriendOption, PictureItem, ShuoshuoItem, build_comment_item

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresSource:
    """基于 PostgreSQL 的只读数据源。"""

    def __init__(self, dsn: str, schema: str) -> None:
        if not dsn.strip():
            raise ConfigError("postgres 数据源需要配置 storage.postgres_dsn")
        if not _SCHEMA_RE.fullmatch(schema):
            raise ConfigError("storage.postgres_schema 仅允许字母、数字、下划线，且不能以数字开头")
        self._dsn = dsn
        self._schema = schema
        self._psycopg = self._load_psycopg()

    def list_friends(self) -> List[FriendOption]:
        """列出数据库中所有已入库好友 QQ。"""
        stmt = self._sql(
            """
            SELECT target_qq, COUNT(*)
            FROM {schema}.qqfetch_shuoshuo
            GROUP BY target_qq
            ORDER BY target_qq ASC
            """
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(stmt)
                return [FriendOption(target_qq=int(row[0]), count=int(row[1]), source="postgres") for row in cur.fetchall()]

    def list_shuoshuo(
        self,
        target_qq: int,
        page: int,
        page_size: int,
        sort: str,
        start_ts: int | None,
        end_ts: int | None,
    ) -> Tuple[List[ShuoshuoItem], int]:
        """查询数据库说说分页结果。"""
        where_sql, params = self._where_clause(target_qq, start_ts, end_ts)
        count_stmt = self._sql(f"SELECT COUNT(*) FROM {{schema}}.qqfetch_shuoshuo {where_sql}")
        order = "ASC" if sort == "asc" else "DESC"
        data_stmt = self._sql(
            f"""
            SELECT tid, content, created_time, like_count, comment_count
            FROM {{schema}}.qqfetch_shuoshuo
            {where_sql}
            ORDER BY created_time {order}
            LIMIT %s OFFSET %s
            """
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(count_stmt, params)
                total = int(cur.fetchone()[0])
                cur.execute(data_stmt, [*params, page_size, (page - 1) * page_size])
                rows = cur.fetchall()
                tids = [str(row[0]) for row in rows]
                pictures_map = self._load_pictures(cur, target_qq, tids)
        items: List[ShuoshuoItem] = []
        for tid, content, created_time, like_count, comment_count in rows:
            items.append(
                ShuoshuoItem(
                    tid=str(tid),
                    content=str(content or ""),
                    created_time=int(created_time or 0),
                    created_time_text=self._format_ts(int(created_time or 0)),
                    like_count=int(like_count or 0),
                    comment_count=int(comment_count or 0),
                    pictures=pictures_map.get(str(tid), []),
                    has_comments=int(comment_count or 0) > 0,
                )
            )
        return items, total

    def list_comments(
        self,
        target_qq: int,
        tid: str,
        page: int,
        page_size: int,
    ) -> Tuple[List[CommentItem], int]:
        """查询数据库评论分页结果。"""
        count_stmt = self._sql(
            """
            SELECT COUNT(*)
            FROM {schema}.qqfetch_comment
            WHERE target_qq = %s AND tid = %s
            """
        )
        data_stmt = self._sql(
            """
            SELECT comment_id, content, created_time, author_uin, author_name
            FROM {schema}.qqfetch_comment
            WHERE target_qq = %s AND tid = %s
            ORDER BY created_time ASC
            LIMIT %s OFFSET %s
            """
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(count_stmt, (target_qq, tid))
                total = int(cur.fetchone()[0])
                cur.execute(data_stmt, (target_qq, tid, page_size, (page - 1) * page_size))
                rows = cur.fetchall()
        items = [
            build_comment_item(
                {
                    "comment_id": str(row[0] or ""),
                    "content": str(row[1] or ""),
                    "created_time": int(row[2] or 0),
                    "author_uin": str(row[3] or ""),
                    "author_name": str(row[4] or ""),
                }
            )
            for row in rows
        ]
        return items, total

    def _load_pictures(
        self,
        cur,
        target_qq: int,
        tids: Sequence[str],
    ) -> Dict[str, List[PictureItem]]:
        """批量读取当前页说说的图片。"""
        if not tids:
            return {}
        stmt = self._sql(
            """
            SELECT tid, pic_id, url, width, height, sort_index
            FROM {schema}.qqfetch_picture
            WHERE target_qq = %s AND tid = ANY(%s)
            ORDER BY tid ASC, sort_index ASC
            """
        )
        cur.execute(stmt, (target_qq, list(tids)))
        out: Dict[str, List[PictureItem]] = {}
        for tid, pic_id, url, width, height, _sort_index in cur.fetchall():
            out.setdefault(str(tid), []).append(
                PictureItem(
                    pic_id=str(pic_id or ""),
                    url=str(url or ""),
                    width=int(width or 0),
                    height=int(height or 0),
                )
            )
        return out

    def _where_clause(
        self,
        target_qq: int,
        start_ts: int | None,
        end_ts: int | None,
    ) -> Tuple[str, List[int]]:
        """构造说说列表过滤条件。"""
        clauses = ["target_qq = %s"]
        params: List[int] = [target_qq]
        if start_ts is not None:
            clauses.append("created_time >= %s")
            params.append(start_ts)
        if end_ts is not None:
            clauses.append("created_time <= %s")
            params.append(end_ts)
        return "WHERE " + " AND ".join(clauses), params

    def _sql(self, template: str):
        """把 schema 安全注入 SQL 模板。"""
        return template.replace("{schema}", self._schema)

    def _connect(self):
        """创建数据库连接。"""
        return self._psycopg.connect(self._dsn, autocommit=True)

    @staticmethod
    def _format_ts(ts: int) -> str:
        """格式化时间戳。"""
        from ..schemas import format_ts

        return format_ts(ts)

    @staticmethod
    def _load_psycopg():
        """按需导入 psycopg。"""
        try:
            return importlib.import_module("psycopg")
        except ModuleNotFoundError as exc:
            raise ConfigError("Web PostgreSQL 数据源需要安装 psycopg>=3.2") from exc
