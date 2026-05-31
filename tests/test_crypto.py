"""crypto 纯函数单测:与独立参考实现交叉验证,并钉死关键向量与边界。"""

from __future__ import annotations

import pytest

from qqfetch.crypto import g_tk, hash33, ptqrtoken
from qqfetch.errors import AuthError

_MASK = 0x7FFFFFFF


def _hash33_ref(s: str, seed: int) -> int:
    """独立参考实现:用 *33 表达且每步取模,代码路径与主实现不同,用于交叉验证。"""
    acc = seed
    for ch in s:
        acc = (acc * 33 + ord(ch)) & _MASK
    return acc


_SAMPLES = [
    "",
    "0",
    "a",
    "ab",
    "AC9876543210",                          # 类 qrsig 样式
    "@k1Lm2nO3pQ-",                          # 含符号(p_skey 常见样式)
    "1234567890abcdefABCDEF",
    "abcdefghijklmnopqrstuvwxyz0123456789",
]


@pytest.mark.parametrize("seed", [0, 5381])
@pytest.mark.parametrize("s", _SAMPLES)
def test_hash33_matches_reference(s, seed):
    """主实现与独立参考实现在多组样本、两种 seed 下完全一致。"""
    assert hash33(s, seed=seed) == _hash33_ref(s, seed)


@pytest.mark.parametrize("seed", [0, 5381])
@pytest.mark.parametrize("s", _SAMPLES)
def test_hash33_in_range(s, seed):
    """结果始终落在 31 位无符号范围 [0, 2^31-1]。"""
    assert 0 <= hash33(s, seed=seed) <= _MASK


def test_hash33_known_vectors():
    """钉死手算可验证的边界向量。"""
    assert hash33("", seed=5381) == 5381          # 空串返回 seed
    assert hash33("", seed=0) == 0
    # "0": e=5381 -> 5381 + 5381*32 + 48 = 177621
    assert hash33("0", seed=5381) == 177621


def test_ptqrtoken_uses_seed_zero():
    """ptqrtoken 使用 seed=0,等价于 hash33(qrsig, 0)。"""
    assert ptqrtoken("") == 0
    assert ptqrtoken("0") == 48                   # 0 + 0 + 48
    assert ptqrtoken("abc") == hash33("abc", seed=0)


def test_g_tk_prefers_p_skey():
    """g_tk 优先用 p_skey(seed=5381)。"""
    assert g_tk("somepskey") == hash33("somepskey", seed=5381)


def test_g_tk_falls_back_to_skey():
    """p_skey 为空时回退 skey。"""
    assert g_tk(None, "myskey") == hash33("myskey", seed=5381)
    assert g_tk("", "myskey") == hash33("myskey", seed=5381)


def test_g_tk_raises_when_both_empty():
    """p_skey 与 skey 均空时抛 AuthError。"""
    with pytest.raises(AuthError):
        g_tk(None, None)
    with pytest.raises(AuthError):
        g_tk("", "")


def test_seed_difference_matters():
    """同一输入在 seed=0 与 seed=5381 下结果不同(防止 seed 退化)。"""
    assert hash33("abc", seed=0) != hash33("abc", seed=5381)
