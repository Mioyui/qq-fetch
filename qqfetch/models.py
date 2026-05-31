"""领域数据模型。

使用 dataclass 描述抓取得到的对象。Shuoshuo 保留原始 JSON(raw),
便于接口字段变动时事后补救,而不必重新抓取。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Picture:
    """说说中的一张图片。"""

    pic_id: str        # 图片唯一标识(接口提供,缺失时由 URL 派生)
    url: str           # 实际用于下载的 URL(尽量为原图)
    width: int = 0
    height: int = 0

    def dedup_key(self) -> str:
        """图片去重键:优先用接口的 pic_id,缺失则退回 URL。"""
        return self.pic_id or self.url


@dataclass
class Comment:
    """说说下的一条评论。"""

    comment_id: str
    content: str
    created_time: int          # Unix 时间戳(秒)
    author_uin: str = ""
    author_name: str = ""


@dataclass
class Shuoshuo:
    """一条说说。"""

    tid: str                                            # 说说唯一 ID
    content: str                                        # 正文
    created_time: int                                   # 发布时间戳(秒)
    like_count: int = 0
    comment_count: int = 0
    pictures: List[Picture] = field(default_factory=list)
    comments: List[Comment] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)   # 原始 JSON,便于补救

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 化的 dict(用于 JSONL 落盘)。"""
        return asdict(self)
