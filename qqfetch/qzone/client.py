"""QzoneClient:注入 g_tk 调用数据接口,并通过 URL 白名单从结构上保证无痕。

核心无痕约束:本类只请求固定的数据接口 emotion_cgi_msglist_v6,绝不构造或
请求目标空间主页(user.qzone.qq.com/{qq});_assert_traceless 对任何出站 URL
做兜底断言,命中主页模式立即抛错。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Mapping

from ..crypto import g_tk
from ..errors import (
    LoginExpiredError,
    QzoneApiError,
    RateLimitedError,
    TracelessViolationError,
)
from ..http_client import HttpClient
from ..logging_setup import get_logger

_log = get_logger(__name__)

MSGLIST = (
    "https://h5.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
)

# 匹配"目标空间主页"——会触发访客记录的留痕入口,必须拒绝
_HOMEPAGE_RE = re.compile(r"user\.qzone\.qq\.com/\d+")

# 登录态失效相关 code(经验值,以实测为准调整)
_EXPIRED_CODES = {-3000, -4002, -10000, 4002, -10001}
# 频率风控相关 code(经验值)
_RATE_LIMIT_CODES = {-10073, -110, 100}


class QzoneClient:
    """封装 g_tk 注入与 msglist 调用。"""

    def __init__(
        self,
        http: HttpClient,
        cookies: Mapping[str, str],
        login_uin: int,
    ) -> None:
        self._http = http
        self._login_uin = login_uin
        self._gtk = g_tk(cookies.get("p_skey"), cookies.get("skey"))

    @property
    def gtk(self) -> int:
        return self._gtk

    def _assert_traceless(self, url: str) -> None:
        """无痕兜底:拒绝任何指向目标空间主页的请求。"""
        if _HOMEPAGE_RE.search(url):
            raise TracelessViolationError(f"拒绝请求会留痕的主页 URL: {url}")

    def call_msglist(self, host_uin: int, pos: int, num: int) -> Dict[str, Any]:
        """调用说说列表接口,返回校验后的原始 JSON(code==0)。"""
        self._assert_traceless(MSGLIST)  # 固定接口,断言兜底防回归
        params = {
            # QQ 空间 msglist 接口用 uin/hostUin 指定被读取的空间主人；
            # 登录账号只通过 Cookie 与 g_tk 体现访问权限。
            "uin": host_uin,
            "hostUin": host_uin,
            "pos": pos,
            "num": num,
            "g_tk": self._gtk,
            "format": "json",
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "code_version": 1,
            "need_private_comment": 1,
            "replynum": 100,
            "sort": 0,
        }
        # Referer 指向"自己"的空间(仅作请求头,不发起对它的 GET),符合接口要求且不留痕
        referer = f"https://user.qzone.qq.com/{self._login_uin}"
        resp = self._http.get(MSGLIST, params=params, referer=referer, throttle=True)
        return self._parse_response(resp)

    def _parse_response(self, resp) -> Dict[str, Any]:
        head = resp.text[:500]
        if resp.status_code in (301, 302, 303, 307, 308) or "ptlogin" in head.lower():
            raise LoginExpiredError("接口重定向/返回登录页,登录态失效")
        data = self._extract_json(resp.text)
        code = int(data.get("code", data.get("ret", 0)) or 0)
        subcode = int(data.get("subcode", 0) or 0)
        message = str(data.get("message") or data.get("msg") or "")
        if code in _EXPIRED_CODES:
            raise LoginExpiredError(f"登录态失效 code={code}: {message}")
        if code in _RATE_LIMIT_CODES:
            raise RateLimitedError(code, message, subcode)
        if code != 0:
            raise QzoneApiError(code, message, subcode)
        return data

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """接口可能返回纯 JSON 或 _Callback({...}) 包裹,统一抽取 JSON 对象。"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        raise QzoneApiError(-1, f"无法解析接口返回: {text[:200]!r}")
