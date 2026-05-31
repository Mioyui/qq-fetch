"""通用小工具。"""

from __future__ import annotations

from typing import Any, Mapping, Optional


def first_present(d: Mapping, *keys: str) -> Optional[Any]:
    """返回字典中第一个存在且非 None 的键值;都没有则返回 None。

    注意:值为 0 或 "" 视为存在(可能是合法值),只跳过缺失或 None 的键。
    """
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None
