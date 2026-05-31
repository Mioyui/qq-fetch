"""登录态持久化:把 cookie 与元数据存为本地 JSON,实现免重复扫码。

过期判定不靠 TTL 猜测,而由业务层惰性验证(首次接口调用失败 → 清除重登)。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from ..logging_setup import get_logger

_log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class SavedSession:
    """持久化的登录态。"""

    cookies: Dict[str, str]
    uin: int
    nickname: str = ""
    saved_at: str = field(default_factory=_now_iso)


class SessionStore:
    """登录态读写。save 使用临时文件 + rename 原子替换,避免写一半损坏。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @staticmethod
    def default_path(uin: int) -> Path:
        return Path.home() / ".qqfetch" / f"{uin}.cookies.json"

    def load(self) -> Optional[SavedSession]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return SavedSession(
                cookies=dict(data["cookies"]),
                uin=int(data["uin"]),
                nickname=data.get("nickname", ""),
                saved_at=data.get("saved_at", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            _log.warning("读取登录态失败,将重新登录: %s", exc)
            return None

    def save(self, session: SavedSession) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(
            json.dumps(asdict(session), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)  # 原子替换
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def clear(self) -> None:
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
