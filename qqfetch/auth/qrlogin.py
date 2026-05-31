"""QQ 扫码登录状态机(ptlogin2)。

流程:request_qrcode(出码+qrsig) → 循环 poll_once(轮询 ptqrlogin)
→ 成功后 finalize(跟随 check_sig 重定向收集 p_skey/skey/uin)。

ptuiCB 回调的解析拆为纯函数 parse_ptuicb,便于单测。
注:具体参数与状态码语义可能随腾讯调整,以 scripts/probe_login.py 实测为准。
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from ..crypto import ptqrtoken
from ..errors import LoginTimeoutError
from ..http_client import HttpClient
from ..logging_setup import get_logger

_log = get_logger(__name__)

APPID = 549000912  # QQ 空间 appid
PTQRSHOW = "https://ssl.ptlogin2.qq.com/ptqrshow"
PTQRLOGIN = "https://ssl.ptlogin2.qq.com/ptqrlogin"
_LOGIN_REFERER = "https://xui.ptlogin2.qq.com/"

# ptqrlogin 返回的状态码(语义以实测为准,轮询逻辑按"成功/过期/进行中"三分以降低耦合)
STATUS_SUCCESS = 0
STATUS_EXPIRED = 65

_PTUICB_RE = re.compile(r"'(.*?)'")


@dataclass
class PollResult:
    """一次轮询结果。"""

    code: int
    check_sig_url: Optional[str]
    message: str
    nickname: str
    raw: str

    @property
    def is_success(self) -> bool:
        return self.code == STATUS_SUCCESS

    @property
    def is_expired(self) -> bool:
        return self.code == STATUS_EXPIRED


@dataclass
class QrSession:
    """一次出码得到的二维码与配套 qrsig。"""

    qrsig: str
    png: bytes


def parse_ptuicb(text: str) -> PollResult:
    """解析 ptqrlogin 返回的 ptuiCB('a','b',url,'d',message,nickname) 回调(纯函数)。

    用单引号内容序列定位各字段:0=状态码 2=check_sig URL 4=提示消息 5=昵称。
    """
    args = _PTUICB_RE.findall(text)
    if not args:
        raise ValueError(f"无法解析 ptuiCB 回调: {text!r}")

    def at(i: int) -> str:
        return args[i] if i < len(args) else ""

    try:
        code = int(at(0))
    except ValueError:
        code = -1
    return PollResult(
        code=code,
        check_sig_url=at(2) or None,
        message=at(4),
        nickname=at(5),
        raw=text,
    )


def extract_uin(cookies: Mapping[str, str]) -> int:
    """从 cookie 的 uin/p_uin(形如 o0123456789)解析出纯数字 QQ 号。"""
    raw = cookies.get("uin") or cookies.get("p_uin") or ""
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else 0


class QrLogin:
    """扫码登录状态机。"""

    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self.nickname: str = ""

    def request_qrcode(self) -> QrSession:
        """请求二维码:返回 PNG,并将 qrsig 存入共享 cookie jar。"""
        params = {
            "appid": APPID,
            "e": "2",
            "l": "M",
            "s": "3",
            "d": "72",
            "v": "4",
            "t": str(random.random()),
            "daid": "5",
            "pt_3rd_aid": "0",
        }
        resp = self._http.get(PTQRSHOW, params=params, referer=_LOGIN_REFERER, throttle=False)
        qrsig = self._http.cookie_dict().get("qrsig", "")
        if not qrsig:
            qrsig = resp.cookies.get("qrsig", "")
        if not qrsig:
            raise LoginTimeoutError("未能获取 qrsig(二维码请求失败)")
        return QrSession(qrsig=qrsig, png=resp.content)

    def poll_once(self, qrsig: str) -> PollResult:
        """轮询一次扫码状态。"""
        params = {
            "u1": "https://qzone.qq.com/",
            "ptqrtoken": str(ptqrtoken(qrsig)),
            "ptredirect": "0",
            "h": "1",
            "t": "1",
            "g": "1",
            "from_ui": "1",
            "ptlang": "2052",
            "action": "0-0-{}".format(int(time.time() * 1000)),
            "js_ver": "20102616",
            "js_type": "1",
            "login_sig": "",
            "pt_uistyle": "40",
            "aid": APPID,
            "daid": "5",
        }
        resp = self._http.get(PTQRLOGIN, params=params, referer=_LOGIN_REFERER, throttle=False)
        return parse_ptuicb(resp.text)

    def finalize(self, check_sig_url: str) -> Dict[str, str]:
        """跟随 check_sig 重定向链,收集最终登录 cookie(p_skey/skey/uin 等)。"""
        self._http.get(check_sig_url, follow_redirects=True, throttle=False)
        return self._http.cookie_dict()

    def run(self, display, *, poll_interval: float = 2.0, timeout: float = 120.0) -> Dict[str, str]:
        """编排完整扫码登录,返回登录成功后的完整 cookie 字典。"""
        session = self.request_qrcode()
        display.show(session.png)
        display.status("请用手机 QQ 扫描二维码并确认登录…")
        deadline = time.monotonic() + timeout
        last_code: Optional[int] = None
        while time.monotonic() < deadline:
            result = self.poll_once(session.qrsig)
            if result.is_success:
                self.nickname = result.nickname
                display.status(f"登录成功:{result.nickname}")
                cookies = self.finalize(result.check_sig_url or "")
                return cookies
            if result.is_expired:
                display.status("二维码已过期,重新获取…")
                session = self.request_qrcode()
                display.show(session.png)
            elif result.code != last_code:
                display.status(f"状态:{result.message}")
            last_code = result.code
            time.sleep(poll_interval)
        raise LoginTimeoutError("扫码登录超时,请重试")
