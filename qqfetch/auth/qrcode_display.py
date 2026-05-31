"""二维码呈现:默认保存 PNG 并用系统默认程序打开;可选终端 ASCII(需 Pillow)。"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Protocol

from ..logging_setup import get_logger

_log = get_logger(__name__)


class QrDisplay(Protocol):
    """二维码呈现接口。"""

    def show(self, png: bytes) -> None: ...
    def status(self, msg: str) -> None: ...
    def close(self) -> None: ...


def _open_file(path: Path) -> None:
    """用系统默认程序打开文件,跨平台兜底到浏览器。"""
    try:
        if sys.platform.startswith("win"):
            getattr(os, "startfile")(str(path))  # 仅 Windows 存在
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:  # noqa: BLE001 - 打开失败不应中断登录
        try:
            webbrowser.open(path.as_uri())
        except Exception:  # noqa: BLE001
            _log.warning("无法自动打开二维码,请手动打开: %s", path)


class FileQrDisplay:
    """保存二维码 PNG 到临时文件并打开(默认、最可靠)。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(tempfile.gettempdir()) / "qqfetch_qr.png"

    def show(self, png: bytes) -> None:
        self._path.write_bytes(png)
        _open_file(self._path)
        print(f"二维码已保存并打开:{self._path}")

    def status(self, msg: str) -> None:
        print(msg)

    def close(self) -> None:
        try:
            self._path.unlink()
        except OSError:
            pass


class AsciiQrDisplay:
    """终端 ASCII 渲染二维码(需 Pillow);失败时回退到 FileQrDisplay。

    从已有 PNG 采样,用半块字符压缩行高以接近正方形比例。黑底终端下
    白模块用亮块、黑模块留空(反相),多数手机扫码可识别;若难以扫描请改用 file 模式。
    """

    def __init__(self, size: int = 50) -> None:
        self._size = size
        self._fallback = FileQrDisplay()

    def show(self, png: bytes) -> None:
        try:
            from PIL import Image
        except ImportError:
            print("未安装 Pillow,无法终端渲染二维码,回退到文件模式。")
            self._fallback.show(png)
            return
        img = Image.open(io.BytesIO(png)).convert("L").resize((self._size, self._size))
        px = img.load()
        threshold = 128
        lines = []
        for y in range(0, self._size, 2):
            row = []
            for x in range(self._size):
                top_light = px[x, y] >= threshold
                bottom_light = px[x, y + 1] >= threshold if y + 1 < self._size else True
                if top_light and bottom_light:
                    row.append("█")
                elif top_light:
                    row.append("▀")
                elif bottom_light:
                    row.append("▄")
                else:
                    row.append(" ")
            lines.append("".join(row))
        print("\n".join(lines))

    def status(self, msg: str) -> None:
        print(msg)

    def close(self) -> None:
        self._fallback.close()


def make_display(mode: str) -> QrDisplay:
    """按配置创建二维码呈现器。"""
    return AsciiQrDisplay() if mode == "ascii" else FileQrDisplay()
