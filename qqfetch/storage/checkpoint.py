"""断点续传游标:记录已抓到的 pos 与已见 tid 集合,每页推进后原子写盘。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List, Set

from ..logging_setup import get_logger

_log = get_logger(__name__)


class Checkpoint:
    """抓取进度:pos(下一页起点)与 seen_tids(已处理的说说 ID)。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self.pos: int = 0
        self.seen_tids: Set[str] = set()

    @classmethod
    def load(cls, path: Path) -> "Checkpoint":
        cp = cls(path)
        if cp._path.exists():
            try:
                data = json.loads(cp._path.read_text(encoding="utf-8"))
                cp.pos = int(data.get("pos", 0))
                cp.seen_tids = set(data.get("seen_tids", []))
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                _log.warning("断点文件损坏,从头开始: %s", exc)
        return cp

    def seen(self, tid: str) -> bool:
        return tid in self.seen_tids

    def advance(self, new_pos: int, tids: Iterable[str]) -> None:
        """推进到新位置并登记本页 tid,随后原子落盘。"""
        self.pos = new_pos
        self.seen_tids.update(tids)
        self._save()

    def reset(self) -> None:
        """清空进度(重新全量抓取时使用)。"""
        self.pos = 0
        self.seen_tids = set()
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        payload = {"pos": self.pos, "seen_tids": sorted(self.seen_tids)}
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)  # 原子替换,避免写一半损坏
