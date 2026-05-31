"""配置加载:从 config.toml 读取并提供默认值;CLI 参数可进一步覆盖。

toml 解析库只在确实需要读取文件时才导入,使默认配置在无 tomli 的旧版本上也可用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .errors import ConfigError

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class Config:
    """运行配置(字段对应 config.toml 各节)。"""

    # target
    target_qq: int = 0
    # fetch
    page_size: int = 20
    max_count: int = 0
    download_images: bool = True
    image_concurrency: int = 1
    original_image: bool = True
    # network
    delay_min: float = 1.0
    delay_max: float = 3.0
    max_retries: int = 3
    timeout: float = 15.0
    user_agent: str = _DEFAULT_UA
    proxy: str = ""
    # storage
    data_dir: str = "./data"
    storage_format: str = "jsonl"
    session_path: str = ""
    # login
    qr_mode: str = "file"
    poll_interval: float = 2.0
    login_timeout: float = 120.0

    @property
    def delay_range(self) -> Tuple[float, float]:
        return (self.delay_min, self.delay_max)


def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - 环境缺失
            raise ConfigError("缺少 TOML 解析库,请安装 tomli(Python<3.11)") from exc
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(path: Optional[str] = None) -> Config:
    """加载配置;文件不存在时返回默认配置。"""
    cfg = Config()
    p = Path(path) if path else Path("config.toml")
    if not p.exists():
        return cfg
    data = _load_toml(p)
    _apply(cfg, data)
    return cfg


def _apply(cfg: Config, data: Dict[str, Any]) -> None:
    t = data.get("target", {})
    cfg.target_qq = int(t.get("qq", cfg.target_qq) or 0)

    fetch = data.get("fetch", {})
    cfg.page_size = int(fetch.get("page_size", cfg.page_size))
    cfg.max_count = int(fetch.get("max_count", cfg.max_count))
    cfg.download_images = bool(fetch.get("download_images", cfg.download_images))
    cfg.image_concurrency = int(fetch.get("image_concurrency", cfg.image_concurrency))
    cfg.original_image = bool(fetch.get("original_image", cfg.original_image))

    net = data.get("network", {})
    cfg.delay_min = float(net.get("delay_min", cfg.delay_min))
    cfg.delay_max = float(net.get("delay_max", cfg.delay_max))
    cfg.max_retries = int(net.get("max_retries", cfg.max_retries))
    cfg.timeout = float(net.get("timeout", cfg.timeout))
    cfg.user_agent = str(net.get("user_agent", cfg.user_agent)) or _DEFAULT_UA
    cfg.proxy = str(net.get("proxy", cfg.proxy))

    st = data.get("storage", {})
    cfg.data_dir = str(st.get("data_dir", cfg.data_dir))
    cfg.storage_format = str(st.get("storage_format", cfg.storage_format))
    cfg.session_path = str(st.get("session_path", cfg.session_path))

    lg = data.get("login", {})
    cfg.qr_mode = str(lg.get("qr_mode", cfg.qr_mode))
    cfg.poll_interval = float(lg.get("poll_interval", cfg.poll_interval))
    cfg.login_timeout = float(lg.get("login_timeout", cfg.login_timeout))
