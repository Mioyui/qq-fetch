"""pic 字段 → 可下载的图片 URL(纯函数)。

url1/url2/url3 哪个是原图各资料不一,故字段优先顺序可由 prefer_original 切换,
并以 scripts/probe_msglist.py 实测结果为准调整 _ORIGINAL_ORDER。
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..models import Picture
from ..utils import first_present

# 尽量取原图时的字段优先顺序;取小图省流量时用 _SMALL_ORDER
_ORIGINAL_ORDER = ("url3", "url2", "url1", "url", "b_url", "original_url")
_SMALL_ORDER = ("url1", "url2", "url3", "url")


def _normalize(url: str) -> str:
    """统一 URL:还原转义斜杠与 &amp;,补全协议为 https。"""
    url = url.replace("\\/", "/").replace("&amp;", "&")
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def to_original_url(pic: Dict[str, Any], *, prefer_original: bool = True) -> str:
    """按字段优先顺序取出一个可用 URL 并规范化;无则返回空串。"""
    order = _ORIGINAL_ORDER if prefer_original else _SMALL_ORDER
    for key in order:
        v = pic.get(key)
        if v:
            return _normalize(str(v))
    return ""


def extract_pictures(item: Dict[str, Any], *, prefer_original: bool = True) -> List[Picture]:
    """从一条说说的 pic 数组解析出图片列表。pic_id 缺失时由 URL 的 sha1 派生。"""
    out: List[Picture] = []
    for pic in item.get("pic") or []:
        url = to_original_url(pic, prefer_original=prefer_original)
        if not url:
            continue
        pid = str(first_present(pic, "pic_id", "picId", "lloc", "sloc") or "")
        if not pid:
            pid = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        out.append(
            Picture(
                pic_id=pid,
                url=url,
                width=int(first_present(pic, "width", "w") or 0),
                height=int(first_present(pic, "height", "h") or 0),
            )
        )
    return out
