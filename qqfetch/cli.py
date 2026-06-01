"""命令行入口:login(扫码登录)与 fetch(抓取说说)。

fetch 内置错误闭环:登录态失效自动重登并凭断点续抓;风控/中断时保存进度优雅退出。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .auth.qrcode_display import make_display
from .auth.qrlogin import QrLogin, extract_uin
from .auth.session_store import SavedSession, SessionStore
from .config import Config, load_config
from .download.image_downloader import ImageDownloader
from .errors import ConfigError, LoginExpiredError, RateLimitedError
from .http_client import HttpClient
from .logging_setup import setup_logging
from .qzone.client import QzoneClient
from .qzone.msglist import MsglistFetcher
from .storage.checkpoint import Checkpoint
from .storage.repository import make_repository


def _session_store(cfg: Config) -> SessionStore:
    path = cfg.session_path or str(Path(cfg.data_dir) / "session.json")
    return SessionStore(Path(path))


def ensure_login(cfg: Config, *, force: bool = False) -> SavedSession:
    """获取登录态:优先复用已保存的;force 或无则扫码登录并保存。"""
    store = _session_store(cfg)
    if not force:
        saved = store.load()
        if saved:
            print(f"复用已保存的登录态(uin={saved.uin},昵称={saved.nickname})")
            return saved
    http = HttpClient(
        user_agent=cfg.user_agent, delay_range=(0, 0),
        timeout=cfg.timeout, proxy=cfg.proxy or None,
    )
    try:
        login = QrLogin(http)
        display = make_display(cfg.qr_mode)
        cookies = login.run(display, poll_interval=cfg.poll_interval, timeout=cfg.login_timeout)
        display.close()
        uin = extract_uin(cookies)
        saved = SavedSession(cookies=cookies, uin=uin, nickname=login.nickname)
        store.save(saved)
        print(f"登录成功并已保存(uin={uin})")
        return saved
    finally:
        http.close()


def run_fetch(cfg: Config, *, reset: bool = False) -> int:
    """抓取主流程,含登录失效自动重登与优雅中断。"""
    if cfg.storage_format not in ("jsonl", "sqlite", "postgres"):
        raise ConfigError(f"不支持的 storage_format: {cfg.storage_format}(仅 jsonl / sqlite / postgres)")

    target_dir = Path(cfg.data_dir) / str(cfg.target_qq)
    target_dir.mkdir(parents=True, exist_ok=True)
    cp_path = target_dir / "checkpoint.json"
    if cfg.storage_format == "jsonl":
        repo_path = target_dir / "shuoshuo.jsonl"
    elif cfg.storage_format == "sqlite":
        repo_path = target_dir / "shuoshuo.sqlite"
    else:
        repo_path = target_dir / "shuoshuo.postgres"
    images_dir = target_dir / "images"

    cp = Checkpoint.load(cp_path)
    if reset:
        cp.reset()
    repo = make_repository(
        cfg.storage_format,
        str(repo_path),
        target_qq=cfg.target_qq,
        postgres_dsn=cfg.postgres_dsn,
        postgres_schema=cfg.postgres_schema,
        postgres_auto_init=cfg.postgres_auto_init,
    )

    session = ensure_login(cfg)
    stats = {"shuoshuo": 0, "images": 0, "image_failed": 0}
    relogin_attempts = 0

    def on_page(pos: int, total: int) -> None:
        print(f"  …抓取中 pos={pos} 已入库={repo.count()} 估计总数={total or '未知'}")

    while True:
        http = HttpClient(
            user_agent=cfg.user_agent, cookies=session.cookies,
            delay_range=cfg.delay_range, max_retries=cfg.max_retries,
            timeout=cfg.timeout, proxy=cfg.proxy or None,
        )
        client = QzoneClient(http, session.cookies, session.uin)
        downloader = (
            ImageDownloader(http, images_dir, concurrency=cfg.image_concurrency)
            if cfg.download_images else None
        )
        fetcher = MsglistFetcher(
            client, repo, cp,
            page_size=cfg.page_size, max_count=cfg.max_count,
            prefer_original=cfg.original_image, on_page=on_page,
        )
        try:
            for sh in fetcher.fetch_all(cfg.target_qq):
                stats["shuoshuo"] += 1
                if downloader:
                    for r in downloader.download_for(sh):
                        if not r.ok:
                            stats["image_failed"] += 1
                        elif r.path:
                            stats["images"] += 1
            break  # 正常完成
        except LoginExpiredError:
            relogin_attempts += 1
            if relogin_attempts > 2:
                print("多次重新登录后仍失效,已保存进度,请检查账号后重试。")
                break
            print("登录态失效,重新扫码登录后将凭断点续抓…")
            _session_store(cfg).clear()
            session = ensure_login(cfg, force=True)
            continue
        except RateLimitedError as exc:
            print(f"疑似触发频率风控(code={exc.code}),已保存进度。请稍后重新运行以续抓。")
            break
        except KeyboardInterrupt:
            print("\n已中断,进度已保存,可重新运行续抓。")
            break
        finally:
            http.close()

    print(
        f"完成:本次新增说说 {stats['shuoshuo']} 条,下载图片 {stats['images']} 张"
        f"(失败 {stats['image_failed']} 张);累计入库 {repo.count()} 条。数据目录:{target_dir}"
    )
    repo.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qqfetch", description="QQ 空间说说无痕抓取工具")
    p.add_argument("--config", help="配置文件路径(默认 ./config.toml)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="扫码登录并保存登录态")
    pf = sub.add_parser("fetch", help="抓取指定好友的说说")
    pf.add_argument("--target", type=int, help="目标好友 QQ(覆盖配置)")
    pf.add_argument("--max", type=int, dest="max_count", help="最多抓取条数(覆盖配置)")
    pf.add_argument("--no-images", action="store_true", help="不下载图片")
    pf.add_argument("--reset-login", action="store_true", help="忽略已保存登录态,强制重新扫码")
    pf.add_argument("--reset", action="store_true", help="清空断点,重新全量抓取")
    return p


def _force_utf8_output() -> None:
    """Windows 控制台默认 GBK,中文输出可能报错;尽力切到 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    setup_logging()
    cfg = load_config(args.config)

    if args.command == "login":
        ensure_login(cfg, force=True)
        return 0

    # fetch:用 CLI 参数覆盖配置
    if args.target:
        cfg.target_qq = args.target
    if args.max_count is not None:
        cfg.max_count = args.max_count
    if args.no_images:
        cfg.download_images = False
    if cfg.target_qq <= 0:
        raise ConfigError("未指定目标 QQ,请用 --target 或在 config.toml 的 [target] qq 设置")
    if args.reset_login:
        _session_store(cfg).clear()
    return run_fetch(cfg, reset=args.reset)
