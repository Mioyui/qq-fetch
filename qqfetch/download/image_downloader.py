"""图片下载:跨运行去重、按 {tid}_{idx} 命名、按魔数推断扩展名、失败记录、可选并发。

重试与限速由 HttpClient 统一负责;本模块只关注去重、命名、落盘与失败兜底。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Union
from urllib.parse import urlparse

from ..http_client import HttpClient
from ..logging_setup import get_logger
from ..models import Picture, Shuoshuo

_log = get_logger(__name__)

# 图片 CDN 要求的 Referer(请求头值,非对该地址发起 GET)
_IMG_REFERER = "https://user.qzone.qq.com/"


@dataclass
class DownloadResult:
    """单张图片的下载结果。"""

    pic_id: str
    path: Optional[str]
    ok: bool
    error: str = ""


class ImageDownloader:
    """把说说中的图片下载到 root 目录。"""

    def __init__(self, http: HttpClient, root: Union[str, Path], *, concurrency: int = 1) -> None:
        self._http = http
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._concurrency = max(1, concurrency)
        self._index_path = self._root / ".index"
        self._failed_log = self._root / "failed_images.log"
        self._done: Set[str] = self._load_index()

    def _load_index(self) -> Set[str]:
        if self._index_path.exists():
            return {ln for ln in self._index_path.read_text(encoding="utf-8").splitlines() if ln}
        return set()

    def _mark_done(self, key: str) -> None:
        self._done.add(key)
        with self._index_path.open("a", encoding="utf-8") as f:
            f.write(key + "\n")

    def download_for(self, sh: Shuoshuo) -> List[DownloadResult]:
        """下载一条说说的所有图片;并发数>1 时用线程池。"""
        tasks = list(enumerate(sh.pictures))
        if not tasks:
            return []
        if self._concurrency == 1:
            return [self._download_one(sh.tid, idx, pic) for idx, pic in tasks]
        with ThreadPoolExecutor(max_workers=self._concurrency) as ex:
            return list(ex.map(lambda t: self._download_one(sh.tid, t[0], t[1]), tasks))

    def _download_one(self, tid: str, idx: int, pic: Picture) -> DownloadResult:
        key = pic.dedup_key()
        if key in self._done:
            return DownloadResult(pic_id=pic.pic_id, path=None, ok=True)  # 已下载,跳过
        try:
            data = self._http.get_bytes(pic.url, referer=_IMG_REFERER)
        except Exception as exc:  # noqa: BLE001 - 单图失败不应中断整体抓取
            self._record_failure(tid, pic, str(exc))
            return DownloadResult(pic_id=pic.pic_id, path=None, ok=False, error=str(exc))
        path = self._root / f"{tid}_{idx}{self._guess_ext(pic.url, data)}"
        path.write_bytes(data)
        self._mark_done(key)
        return DownloadResult(pic_id=pic.pic_id, path=str(path), ok=True)

    def _record_failure(self, tid: str, pic: Picture, err: str) -> None:
        _log.warning("图片下载失败 tid=%s url=%s: %s", tid, pic.url, err)
        with self._failed_log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"tid": tid, "pic_id": pic.pic_id, "url": pic.url, "error": err},
                    ensure_ascii=False,
                )
                + "\n"
            )

    @staticmethod
    def _guess_ext(url: str, data: bytes) -> str:
        """先按 URL 后缀,再按文件魔数推断扩展名;无法判断时默认 .jpg。"""
        path = urlparse(url).path.lower()
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            if path.endswith(ext):
                return ext
        if data[:3] == b"\xff\xd8\xff":
            return ".jpg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return ".gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        return ".jpg"
