"""自定义异常体系。

所有异常继承自 QQFetchError,便于上层统一捕获与分流处理。
"""

from __future__ import annotations


class QQFetchError(Exception):
    """本项目所有异常的基类。"""


class ConfigError(QQFetchError):
    """配置缺失或非法。"""


class AuthError(QQFetchError):
    """登录态相关错误的基类(如缺少可用的 skey)。"""


class LoginTimeoutError(AuthError):
    """扫码登录超时:二维码过期或用户未在时限内完成扫码确认。"""


class LoginExpiredError(AuthError):
    """已保存的登录态失效,需要重新扫码。"""


class TracelessViolationError(QQFetchError):
    """检测到将要请求会留痕的 URL(如目标空间主页),已阻止以保证无痕。

    这是无痕约束的结构性兜底:任何试图请求目标主页的代码路径都会在此处失败。
    """


class QzoneApiError(QQFetchError):
    """QQ 空间接口返回非成功状态。"""

    def __init__(self, code: int, message: str = "", subcode: int = 0) -> None:
        self.code = code
        self.subcode = subcode
        self.message = message
        super().__init__(f"Qzone API 错误 code={code} subcode={subcode}: {message}")


class RateLimitedError(QzoneApiError):
    """疑似触发频率风控,应退避后重试或暂停。"""
