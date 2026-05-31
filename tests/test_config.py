"""config 单测:默认值、从 TOML 读取、类型转换。"""

from __future__ import annotations

from qqfetch.config import load_config


def test_defaults_without_file(tmp_path):
    cfg = load_config(str(tmp_path / "nonexistent.toml"))
    assert cfg.page_size == 20
    assert cfg.download_images is True
    assert cfg.qr_mode == "file"
    assert cfg.delay_range == (1.0, 3.0)
    assert cfg.storage_format == "jsonl"


def test_load_from_toml(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "\n".join(
            [
                "[target]",
                "qq = 12345",
                "[fetch]",
                "page_size = 5",
                "download_images = false",
                "[network]",
                "delay_min = 0.5",
                "delay_max = 1.5",
                "[storage]",
                'storage_format = "sqlite"',
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.target_qq == 12345
    assert cfg.page_size == 5
    assert cfg.download_images is False
    assert cfg.delay_range == (0.5, 1.5)
    assert cfg.storage_format == "sqlite"
