"""parse_ptuicb 与 extract_uin 纯函数单测:覆盖各状态码与边界。"""

from __future__ import annotations

import pytest

from qqfetch.auth.qrlogin import extract_uin, parse_ptuicb


def test_waiting_state():
    r = parse_ptuicb("ptuiCB('66','0','','0','二维码未失效。','')")
    assert r.code == 66
    assert r.check_sig_url is None
    assert not r.is_success and not r.is_expired


def test_success_state():
    text = (
        "ptuiCB('0','0',"
        "'https://ptlogin2.qzone.qq.com/check_sig?pttype=1&uin=12345&service=login',"
        "'0','登录成功!','小明')"
    )
    r = parse_ptuicb(text)
    assert r.is_success
    assert r.check_sig_url is not None
    assert r.check_sig_url.startswith("https://ptlogin2.qzone.qq.com/check_sig")
    assert "uin=12345" in r.check_sig_url   # URL 内的 & = 不影响单引号字段切分
    assert r.nickname == "小明"


def test_expired_state():
    r = parse_ptuicb("ptuiCB('65','0','','0','二维码已失效。','')")
    assert r.code == 65 and r.is_expired


def test_scanned_state():
    r = parse_ptuicb("ptuiCB('67','0','','0','二维码认证中。','')")
    assert r.code == 67
    assert not r.is_success and not r.is_expired


def test_malformed_raises():
    with pytest.raises(ValueError):
        parse_ptuicb("完全不含回调结构的垃圾文本")


@pytest.mark.parametrize(
    "cookies,expected",
    [
        ({"uin": "o0123456789"}, 123456789),
        ({"p_uin": "o888"}, 888),
        ({"uin": "12345"}, 12345),
        ({}, 0),
        ({"uin": ""}, 0),
    ],
)
def test_extract_uin(cookies, expected):
    assert extract_uin(cookies) == expected
