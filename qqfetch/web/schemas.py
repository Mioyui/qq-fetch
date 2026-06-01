"""Web 浏览页的数据结构定义。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


def format_ts(ts: int) -> str:
    """把 Unix 时间戳格式化为前端展示文本。"""
    if ts <= 0:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


@dataclass
class FriendOption:
    """好友选择项。"""

    target_qq: int
    count: int
    source: str

    def to_dict(self) -> Dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return asdict(self)


@dataclass
class PictureItem:
    """页面展示用的图片项。"""

    pic_id: str
    url: str
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return asdict(self)


@dataclass
class CommentItem:
    """页面展示用的评论项。"""

    comment_id: str
    content: str
    created_time: int
    created_time_text: str
    author_uin: str = ""
    author_name: str = ""

    def to_dict(self) -> Dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return asdict(self)


@dataclass
class ShuoshuoItem:
    """页面展示用的说说项。"""

    tid: str
    content: str
    created_time: int
    created_time_text: str
    like_count: int
    comment_count: int
    pictures: List[PictureItem] = field(default_factory=list)
    has_comments: bool = False

    def to_dict(self) -> Dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        data = asdict(self)
        data["pictures"] = [p.to_dict() for p in self.pictures]
        return data


@dataclass
class PagedShuoshuoResponse:
    """说说分页响应。"""

    items: List[ShuoshuoItem]
    total: int
    total_pages: int
    page: int
    page_size: int
    sort: str
    filter_summary: Dict[str, object]
    selected_target_qq: int

    def to_dict(self) -> Dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "total_pages": self.total_pages,
            "page": self.page,
            "page_size": self.page_size,
            "sort": self.sort,
            "filter_summary": self.filter_summary,
            "selected_target_qq": self.selected_target_qq,
        }


@dataclass
class PagedCommentsResponse:
    """评论分页响应。"""

    items: List[CommentItem]
    total: int
    total_pages: int
    page: int
    page_size: int
    target_qq: int
    tid: str

    def to_dict(self) -> Dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "total_pages": self.total_pages,
            "page": self.page,
            "page_size": self.page_size,
            "target_qq": self.target_qq,
            "tid": self.tid,
        }


def build_picture_item(data: Dict[str, object]) -> PictureItem:
    """从统一字典构造图片项。"""
    return PictureItem(
        pic_id=str(data.get("pic_id") or ""),
        url=str(data.get("url") or ""),
        width=int(data.get("width") or 0),
        height=int(data.get("height") or 0),
    )


def build_comment_item(data: Dict[str, object]) -> CommentItem:
    """从统一字典构造评论项。"""
    created_time = int(data.get("created_time") or 0)
    return CommentItem(
        comment_id=str(data.get("comment_id") or ""),
        content=str(data.get("content") or ""),
        created_time=created_time,
        created_time_text=format_ts(created_time),
        author_uin=str(data.get("author_uin") or ""),
        author_name=str(data.get("author_name") or ""),
    )


def build_shuoshuo_item(data: Dict[str, object]) -> ShuoshuoItem:
    """从统一字典构造说说项。"""
    created_time = int(data.get("created_time") or 0)
    pictures = [build_picture_item(item) for item in list(data.get("pictures") or [])]
    comment_count = int(data.get("comment_count") or 0)
    return ShuoshuoItem(
        tid=str(data.get("tid") or ""),
        content=str(data.get("content") or ""),
        created_time=created_time,
        created_time_text=format_ts(created_time),
        like_count=int(data.get("like_count") or 0),
        comment_count=comment_count,
        pictures=pictures,
        has_comments=comment_count > 0,
    )


def build_filter_summary(
    *,
    source: str,
    preset: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Dict[str, object]:
    """构造当前筛选条件摘要。"""
    return {
        "source": source,
        "preset": preset,
        "start_date": start_date or "",
        "end_date": end_date or "",
    }
