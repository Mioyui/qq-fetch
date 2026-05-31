"""HTTP 客户端封装:全项目唯一出网点。

集中处理 Cookie、公共请求头、限速(请求间随机延时)与重试(指数退避),
业务层不感知这些横切关注点。基于 httpx.Client(连接复用、cookie jar、
精细的重定向控制——扫码登录 finalize 需跟随多跳重定向收集 set-cookie)。
"""

from __future__ import annotations

import random
import time
from typing import Dict, Mapping, Optional, Tuple

import httpx

from .logging_setup import get_logger

_log = get_logger(__name__)

# 公共请求头。User-Agent 在构造时注入。
_DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


class HttpClient:
    """带限速与重试的 HTTP 会话。"""

    def __init__(
        self,
        *,
        user_agent: str,
        cookies: Optional[Mapping[str, str]] = None,
        delay_range: Tuple[float, float] = (1.0, 3.0),
        max_retries: int = 3,
        timeout: float = 15.0,
        proxy: Optional[str] = None,
        backoff_base: float = 1.0,
    ) -> None:
        self._delay_range = delay_range
        self._max_retries = max(0, max_retries)
        self._backoff_base = backoff_base
        headers = dict(_DEFAULT_HEADERS)
        headers["User-Agent"] = user_agent
        kwargs = dict(
            headers=headers,
            cookies=dict(cookies or {}),
            timeout=timeout,
            follow_redirects=False,
        )
        if proxy:
            kwargs["proxy"] = proxy
        self._client = httpx.Client(**kwargs)

    # ---------------- 公共 API ----------------
    def get(
        self,
        url: str,
        *,
        params: Optional[Mapping] = None,
        headers: Optional[Mapping[str, str]] = None,
        referer: Optional[str] = None,
        follow_redirects: bool = False,
        throttle: bool = True,
    ) -> httpx.Response:
        """发起 GET。throttle=True 时请求前随机延时(数据抓取限速;登录轮询可关闭)。"""
        merged = dict(headers or {})
        if referer:
            merged["Referer"] = referer
        return self._send(
            "GET", url, params=params, headers=merged,
            follow_redirects=follow_redirects, throttle=throttle,
        )

    def get_bytes(self, url: str, *, referer: Optional[str] = None, throttle: bool = True) -> bytes:
        """下载二进制内容(图片)。跟随重定向并对非 2xx 抛错。"""
        resp = self.get(url, referer=referer, follow_redirects=True, throttle=throttle)
        resp.raise_for_status()
        return resp.content

    def update_cookies(self, new: Mapping[str, str]) -> None:
        """合并新的 Cookie(登录成功后写入)。"""
        self._client.cookies.update(dict(new))

    def cookie_dict(self) -> Dict[str, str]:
        """导出当前 Cookie 字典。"""
        return dict(self._client.cookies)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------- 内部 ----------------
    def _throttle(self) -> None:
        low, high = self._delay_range
        if high > 0:
            time.sleep(random.uniform(low, high))

    def _send(self, method, url, *, params, headers, follow_redirects, throttle):
        if throttle:
            self._throttle()
        delay = self._backoff_base
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.request(
                    method, url, params=params, headers=headers,
                    follow_redirects=follow_redirects,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    _log.error("请求失败(已重试 %d 次): %s %s", self._max_retries, url, exc)
                    raise
                _log.warning("请求异常,第 %d 次重试: %s", attempt + 1, exc)
            else:
                # 5xx 视为可重试;其余(含 4xx)直接返回,由业务层判定
                if resp.status_code >= 500 and attempt < self._max_retries:
                    _log.warning("服务端 %d,第 %d 次重试: %s", resp.status_code, attempt + 1, url)
                else:
                    return resp
            time.sleep(delay + random.uniform(0, self._backoff_base))
            delay *= 2
        raise RuntimeError("不可达:重试循环必然 return 或 raise")
