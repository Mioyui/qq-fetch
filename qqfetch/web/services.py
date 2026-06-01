"""Web 浏览页查询服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from typing import Optional

from ..config import Config
from ..errors import ConfigError
from .schemas import PagedCommentsResponse, PagedShuoshuoResponse, build_filter_summary
from .sources import ReadonlySource
from .sources.local_source import LocalSource
from .sources.postgres_source import PostgresSource

_VALID_PRESETS = {"all", "7d", "30d", "90d", "1y"}
_VALID_SORTS = {"asc", "desc"}


class BrowserService:
    """浏览页服务入口。"""

    def __init__(self, config: Config) -> None:
        self._config = config

    def list_friends(self, source: str):
        """列出某个数据源下可展示的好友。"""
        return [item.to_dict() for item in self._source(source).list_friends()]

    def list_shuoshuo(
        self,
        *,
        source: str,
        target_qq: int,
        page: int,
        page_size: int,
        sort: str,
        start_date: Optional[str],
        end_date: Optional[str],
        preset: str,
    ) -> dict:
        """查询说说分页结果。"""
        self._validate_target(target_qq)
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        sort = self._validate_sort(sort)
        preset = self._validate_preset(preset)
        start_ts, end_ts = self._resolve_time_range(start_date, end_date, preset)
        items, total = self._source(source).list_shuoshuo(target_qq, page, page_size, sort, start_ts, end_ts)
        return PagedShuoshuoResponse(
            items=items,
            total=total,
            total_pages=max(1, ceil(total / page_size)) if total else 1,
            page=page,
            page_size=page_size,
            sort=sort,
            filter_summary=build_filter_summary(
                source=source,
                preset=preset,
                start_date=start_date,
                end_date=end_date,
            ),
            selected_target_qq=target_qq,
        ).to_dict()

    def list_comments(
        self,
        *,
        source: str,
        target_qq: int,
        tid: str,
        page: int,
        page_size: int,
    ) -> dict:
        """查询评论分页结果。"""
        self._validate_target(target_qq)
        if not tid:
            raise ConfigError("tid 不能为空")
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        items, total = self._source(source).list_comments(target_qq, tid, page, page_size)
        return PagedCommentsResponse(
            items=items,
            total=total,
            total_pages=max(1, ceil(total / page_size)) if total else 1,
            page=page,
            page_size=page_size,
            target_qq=target_qq,
            tid=tid,
        ).to_dict()

    def _source(self, source: str) -> ReadonlySource:
        """按名称解析只读数据源。"""
        if source == "local":
            return LocalSource(self._config.data_dir)
        if source == "postgres":
            return PostgresSource(self._config.postgres_dsn, self._config.postgres_schema)
        raise ConfigError(f"不支持的数据源: {source}")

    @staticmethod
    def _validate_target(target_qq: int) -> None:
        """校验目标 QQ。"""
        if target_qq <= 0:
            raise ConfigError("target_qq 必须为正整数")

    @staticmethod
    def _validate_sort(sort: str) -> str:
        """校验排序方向。"""
        if sort not in _VALID_SORTS:
            raise ConfigError("sort 仅支持 asc 或 desc")
        return sort

    @staticmethod
    def _validate_preset(preset: str) -> str:
        """校验快捷时间区间。"""
        value = preset or "all"
        if value not in _VALID_PRESETS:
            raise ConfigError("preset 仅支持 all/7d/30d/90d/1y")
        return value

    def _resolve_time_range(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        preset: str,
    ) -> tuple[int | None, int | None]:
        """解析显式日期与快捷区间。"""
        if start_date or end_date:
            start_ts = self._parse_date(start_date, end_of_day=False) if start_date else None
            end_ts = self._parse_date(end_date, end_of_day=True) if end_date else None
            return start_ts, end_ts
        now = datetime.now()
        if preset == "all":
            return None, None
        days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}[preset]
        start = now - timedelta(days=days)
        return int(start.timestamp()), int(now.timestamp())

    @staticmethod
    def _parse_date(value: str, *, end_of_day: bool) -> int:
        """把 YYYY-MM-DD 解析为时间戳。"""
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ConfigError("日期格式必须为 YYYY-MM-DD") from exc
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return int(parsed.timestamp())
