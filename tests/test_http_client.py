"""HttpClient 单测:用 respx mock httpx,验证头注入、cookie、限速调用与重试。"""

from __future__ import annotations

import httpx
import pytest
import respx

from qqfetch.http_client import HttpClient


@pytest.fixture
def no_sleep(monkeypatch):
    """消除真实延时,并记录每次 sleep 的时长,便于断言限速/退避是否发生。"""
    calls = []
    monkeypatch.setattr("qqfetch.http_client.time.sleep", lambda s: calls.append(s))
    return calls


@respx.mock
def test_get_injects_referer_and_cookie(no_sleep):
    route = respx.get("https://h5.qzone.qq.com/test").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client = HttpClient(cookies={"p_skey": "x"}, user_agent="UA", delay_range=(0, 0))
    resp = client.get("https://h5.qzone.qq.com/test", referer="https://user.qzone.qq.com/123")
    assert resp.status_code == 200
    assert route.called
    req = route.calls.last.request
    assert req.headers["Referer"] == "https://user.qzone.qq.com/123"
    assert "p_skey=x" in req.headers.get("cookie", "")
    client.close()


@respx.mock
def test_retries_on_5xx_then_succeeds(no_sleep):
    respx.get("https://h5.qzone.qq.com/r").mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, text="ok")]
    )
    client = HttpClient(user_agent="UA", delay_range=(0, 0), max_retries=3, backoff_base=0.01)
    resp = client.get("https://h5.qzone.qq.com/r")
    assert resp.status_code == 200 and resp.text == "ok"
    client.close()


@respx.mock
def test_retries_on_transport_error_then_raises(no_sleep):
    respx.get("https://h5.qzone.qq.com/e").mock(side_effect=httpx.ConnectError("boom"))
    client = HttpClient(user_agent="UA", delay_range=(0, 0), max_retries=2, backoff_base=0.01)
    with pytest.raises(httpx.ConnectError):
        client.get("https://h5.qzone.qq.com/e")
    client.close()


@respx.mock
def test_throttle_called_when_enabled(no_sleep):
    respx.get("https://h5.qzone.qq.com/t").mock(return_value=httpx.Response(200))
    client = HttpClient(user_agent="UA", delay_range=(0.5, 0.5))
    client.get("https://h5.qzone.qq.com/t", throttle=True)
    assert 0.5 in no_sleep        # _throttle 调用 sleep(uniform(0.5,0.5)=0.5)
    client.close()


@respx.mock
def test_no_throttle_when_disabled(no_sleep):
    respx.get("https://h5.qzone.qq.com/n").mock(return_value=httpx.Response(200))
    client = HttpClient(user_agent="UA", delay_range=(0.5, 0.5))
    client.get("https://h5.qzone.qq.com/n", throttle=False)
    assert no_sleep == []         # 未限速、无重试 => 完全无 sleep
    client.close()


@respx.mock
def test_update_and_export_cookies(no_sleep):
    client = HttpClient(user_agent="UA", delay_range=(0, 0))
    client.update_cookies({"skey": "abc", "uin": "o123"})
    cookies = client.cookie_dict()
    assert cookies["skey"] == "abc"
    assert cookies["uin"] == "o123"
    client.close()
