"""QzoneClient 单测:g_tk 注入、JSON/Callback 解析、失效与风控分流、无痕断言。"""

from __future__ import annotations

import httpx
import pytest
import respx

from qqfetch.errors import (
    LoginExpiredError,
    QzoneApiError,
    RateLimitedError,
    TracelessViolationError,
)
from qqfetch.http_client import HttpClient
from qqfetch.qzone.client import MSGLIST, QzoneClient


def _client():
    http = HttpClient(user_agent="UA", delay_range=(0, 0))
    return QzoneClient(http, {"p_skey": "demo"}, login_uin=111)


@respx.mock
def test_injects_gtk_and_host_uin():
    respx.get(url__startswith=MSGLIST).mock(
        return_value=httpx.Response(200, text='{"code":0,"total":1,"msglist":[{"tid":"x"}]}')
    )
    data = _client().call_msglist(222, 0, 20)
    assert data["msglist"][0]["tid"] == "x"
    url = str(respx.calls.last.request.url)
    assert "g_tk=" in url and "hostUin=222" in url and "uin=222" in url


@respx.mock
def test_callback_wrapped_json_parsed():
    respx.get(url__startswith=MSGLIST).mock(
        return_value=httpx.Response(200, text='_Callback({"code":0,"total":0,"msglist":[]});')
    )
    assert _client().call_msglist(222, 0, 20)["msglist"] == []


@respx.mock
def test_expired_code_raises():
    respx.get(url__startswith=MSGLIST).mock(
        return_value=httpx.Response(200, text='{"code":-3000,"message":"need login"}')
    )
    with pytest.raises(LoginExpiredError):
        _client().call_msglist(222, 0, 20)


@respx.mock
def test_login_page_html_raises_expired():
    respx.get(url__startswith=MSGLIST).mock(
        return_value=httpx.Response(200, text="<html>ptlogin redirect</html>")
    )
    with pytest.raises(LoginExpiredError):
        _client().call_msglist(222, 0, 20)


@respx.mock
def test_rate_limit_code_raises():
    respx.get(url__startswith=MSGLIST).mock(
        return_value=httpx.Response(200, text='{"code":-10073,"message":"frequent"}')
    )
    with pytest.raises(RateLimitedError):
        _client().call_msglist(222, 0, 20)


@respx.mock
def test_other_nonzero_code_raises_api_error():
    respx.get(url__startswith=MSGLIST).mock(
        return_value=httpx.Response(200, text='{"code":-1,"message":"err"}')
    )
    with pytest.raises(QzoneApiError):
        _client().call_msglist(222, 0, 20)


def test_traceless_blocks_homepage():
    with pytest.raises(TracelessViolationError):
        _client()._assert_traceless("https://user.qzone.qq.com/222")


def test_traceless_allows_data_api():
    _client()._assert_traceless(MSGLIST)  # 数据接口不应被拦截
