"""CLI 参数解析单测(不触网)。"""

from __future__ import annotations

import pytest

from qqfetch.cli import build_parser


def test_fetch_args():
    a = build_parser().parse_args(["fetch", "--target", "999", "--max", "10", "--no-images"])
    assert a.command == "fetch"
    assert a.target == 999
    assert a.max_count == 10
    assert a.no_images is True
    assert a.reset is False


def test_login_command():
    a = build_parser().parse_args(["login"])
    assert a.command == "login"


def test_reset_flags():
    a = build_parser().parse_args(["fetch", "--target", "1", "--reset", "--reset-login"])
    assert a.reset is True and a.reset_login is True


def test_web_command():
    a = build_parser().parse_args(["web", "--host", "0.0.0.0", "--port", "8765"])
    assert a.command == "web"
    assert a.host == "0.0.0.0"
    assert a.port == 8765


def test_missing_subcommand_errors():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
