"""QQ 系统通用签名算法(hash33)及其衍生。

纯函数,无 IO,是全项目算法基石。腾讯前端用两个 seed 略不同的 hash33 变体:
- 扫码登录的 ptqrtoken: seed = 0
- QQ 空间接口签名 g_tk : seed = 5381
二者主体相同(e = e*33 + charCode,取低 31 位),仅初始值不同。

注:腾讯 JS 原版每步做 `e &= 0x7fffffff` 且 `<<` 按 32 位截断;由于最终只取低 31 位,
而 2^31 整除 2^32,高位截断不影响结果,故此处只在最后取一次 & 0x7fffffff,与 JS 原版等价。
cookie 值均为 ASCII,Python ord 与 JS charCodeAt 一致,无差异。
"""

from __future__ import annotations

from typing import Optional

from .errors import AuthError

_MASK = 0x7FFFFFFF


def hash33(s: str, seed: int = 5381) -> int:
    """腾讯 hash33:e = seed,对每字符 e = e*33 + ord(c),返回低 31 位。"""
    e = seed
    for c in s:
        e += (e << 5) + ord(c)
    return e & _MASK


def ptqrtoken(qrsig: str) -> int:
    """由 qrsig cookie 计算扫码轮询用的 ptqrtoken(seed=0)。"""
    return hash33(qrsig, seed=0)


def g_tk(p_skey: Optional[str], skey: Optional[str] = None) -> int:
    """计算 QQ 空间接口签名 g_tk(seed=5381)。

    优先使用 p_skey;为空时回退 skey;两者皆空抛 AuthError。
    """
    key = p_skey or skey
    if not key:
        raise AuthError("无法计算 g_tk:p_skey 与 skey 均为空")
    return hash33(key, seed=5381)
