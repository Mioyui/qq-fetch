"""说说 JSON → 领域模型(纯函数,多字段名容错,保留 raw 便于补救)。

字段名以 scripts/probe_msglist.py 实测为准;此处对常见命名做兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..models import Comment, Shuoshuo
from ..utils import first_present
from .image_urls import extract_pictures


@dataclass
class ParsedPage:
    """一页解析结果。"""

    items: List[Shuoshuo]
    total: int


def parse_comments(item: Dict[str, Any]) -> List[Comment]:
    """解析评论列表(字段名容错)。"""
    out: List[Comment] = []
    for c in item.get("commentlist") or []:
        out.append(
            Comment(
                comment_id=str(first_present(c, "tid", "commentid", "id") or ""),
                content=c.get("content") or "",
                created_time=int(first_present(c, "create_time", "createTime", "abstime") or 0),
                author_uin=str(first_present(c, "uin", "poster_uin") or ""),
                author_name=str(first_present(c, "name", "nickname", "poster_name") or ""),
            )
        )
    return out


def _like_count(item: Dict[str, Any]) -> int:
    """点赞数在 msglist v6 中位置不固定,做多重兜底。"""
    like = item.get("like")
    if isinstance(like, dict):
        v = first_present(like, "num", "count", "likeNum")
        if v is not None:
            return int(v)
    v = first_present(item, "likeTotal", "like_num", "likecnt")
    return int(v) if v is not None else 0


def parse_shuoshuo(item: Dict[str, Any], *, prefer_original: bool = True) -> Shuoshuo:
    """解析单条说说。"""
    return Shuoshuo(
        tid=str(first_present(item, "tid", "t1d", "id") or ""),
        content=item.get("content") or "",
        created_time=int(first_present(item, "created_time", "abstime", "create_time") or 0),
        like_count=_like_count(item),
        comment_count=int(first_present(item, "cmtnum", "commentcount", "comment_count") or 0),
        pictures=extract_pictures(item, prefer_original=prefer_original),
        comments=parse_comments(item),
        raw=item,
    )


def parse_msglist(payload: Dict[str, Any], *, prefer_original: bool = True) -> ParsedPage:
    """解析一页 msglist 返回。"""
    msglist = payload.get("msglist") or []
    total = int(first_present(payload, "total") or 0)
    items = [parse_shuoshuo(m, prefer_original=prefer_original) for m in msglist]
    return ParsedPage(items=items, total=total)
