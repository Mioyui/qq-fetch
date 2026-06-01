"""说说 JSON → 领域模型(纯函数,多字段名容错,保留 raw 便于补救)。

字段名以 scripts/probe_msglist.py 实测为准;此处对常见命名做兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
        parent = _parse_comment(c)
        out.append(parent)
        # 说说主人的回复通常嵌在顶层评论的 list_3 中，这里一并展开。
        # 复合 comment_id 用于避免子回复和父评论共用 tid 时在下游存储中互相覆盖。
        for idx, child in enumerate(_nested_replies(c), start=1):
            out.append(_parse_comment(child, parent_comment_id=parent.comment_id, reply_index=idx))
    return out


def _parse_comment(
    item: Dict[str, Any],
    *,
    parent_comment_id: Optional[str] = None,
    reply_index: int = 0,
) -> Comment:
    """解析单条评论或回复。"""
    raw_comment_id = str(first_present(item, "tid", "commentid", "id") or "")
    comment_id = raw_comment_id
    if parent_comment_id:
        suffix = raw_comment_id or str(reply_index)
        comment_id = f"{parent_comment_id}:{suffix}"
    return Comment(
        comment_id=comment_id,
        content=item.get("content") or "",
        created_time=int(first_present(item, "create_time", "createTime", "abstime") or 0),
        author_uin=str(first_present(item, "uin", "poster_uin") or ""),
        author_name=str(first_present(item, "name", "nickname", "poster_name") or ""),
    )


def _nested_replies(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """提取评论下的嵌套回复列表。"""
    replies = first_present(item, "list_3", "replylist", "reply_list")
    return list(replies or [])


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
