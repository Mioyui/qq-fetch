"""Web 数据源抽象。"""

from __future__ import annotations

from typing import Protocol, Tuple, List

from ..schemas import CommentItem, FriendOption, ShuoshuoItem


class ReadonlySource(Protocol):
    """只读数据源接口。"""

    def list_friends(self) -> List[FriendOption]:
        """列出当前数据源可用的好友 QQ。"""
        ...

    def list_shuoshuo(
        self,
        target_qq: int,
        page: int,
        page_size: int,
        sort: str,
        start_ts: int | None,
        end_ts: int | None,
    ) -> Tuple[List[ShuoshuoItem], int]:
        """查询说说分页结果。"""
        ...

    def list_comments(
        self,
        target_qq: int,
        tid: str,
        page: int,
        page_size: int,
    ) -> Tuple[List[CommentItem], int]:
        """查询某条说说下的评论分页结果。"""
        ...
