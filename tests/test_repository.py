"""Repository 单测:JSONL / SQLite 的快照保存语义，以及 PostgreSQL 配置校验。"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from qqfetch.errors import ConfigError
from qqfetch.models import Comment, Picture, Shuoshuo
from qqfetch.storage.repository import JsonlRepository, _comment_key, make_repository


def _sh(tid: str) -> Shuoshuo:
    """构造一条最小可保存说说。"""
    return Shuoshuo(
        tid=tid,
        content="c" + tid,
        created_time=100,
        pictures=[Picture(pic_id="p1", url="https://example.com/1.jpg")],
        comments=[Comment(comment_id="c1", content="hi", created_time=101, author_uin="2")],
        raw={"tid": tid},
    )


@pytest.mark.parametrize("fmt", ["jsonl", "sqlite"])
def test_save_count_dedup(tmp_path, fmt):
    """本地仓储保持“首次写入返回 True，重复写入返回 False”的语义。"""
    repo = make_repository(fmt, str(tmp_path / ("d." + fmt)))
    assert repo.save(_sh("t1")) is True
    assert repo.count() == 1
    assert repo.save(_sh("t1")) is False
    assert repo.count() == 1
    assert repo.save(_sh("t2")) is True
    assert repo.count() == 2
    repo.close()


def test_jsonl_reload_index(tmp_path):
    """JSONL 重新打开后仍能识别已写入 tid。"""
    p = str(tmp_path / "d.jsonl")
    r1 = JsonlRepository(p)
    assert r1.save(_sh("a")) is True
    assert r1.save(_sh("b")) is True
    r2 = JsonlRepository(p)
    assert r2.exists("a") and r2.exists("b") and r2.count() == 2


def test_postgres_requires_dsn(tmp_path):
    """PostgreSQL 后端缺少 DSN 时应直接报配置错误。"""
    with pytest.raises(ConfigError):
        make_repository("postgres", str(tmp_path / "unused"), target_qq=1, postgres_dsn="")


def test_postgres_requires_valid_schema(tmp_path):
    """Schema 名只允许安全字符，避免动态 SQL 注入。"""
    with pytest.raises(ConfigError):
        make_repository(
            "postgres",
            str(tmp_path / "unused"),
            target_qq=1,
            postgres_dsn="postgresql://demo",
            postgres_schema="bad-schema",
        )


def test_postgres_requires_driver(tmp_path, monkeypatch):
    """未安装 psycopg 时，PostgreSQL 后端应给出明确错误。"""

    def _boom(name: str):
        if name == "psycopg":
            raise ModuleNotFoundError("missing psycopg")
        return importlib.import_module(name)

    monkeypatch.setattr("qqfetch.storage.repository.importlib.import_module", _boom)
    with pytest.raises(ConfigError):
        make_repository(
            "postgres",
            str(tmp_path / "unused"),
            target_qq=1,
            postgres_dsn="postgresql://demo",
        )


def test_postgres_connect_error_is_readable(tmp_path, monkeypatch):
    """连接失败时应抛出可读的中文配置错误，而不是裸 traceback。"""

    class FakeOperationalError(Exception):
        """模拟 psycopg 的连接异常。"""

    def _connect(_dsn: str):
        raise FakeOperationalError("boom")

    fake_psycopg = SimpleNamespace(
        OperationalError=FakeOperationalError,
        connect=_connect,
        sql=SimpleNamespace(Identifier=object, SQL=object),
        types=SimpleNamespace(json=SimpleNamespace(Jsonb=dict)),
    )

    monkeypatch.setattr(
        "qqfetch.storage.repository.importlib.import_module",
        lambda name: fake_psycopg if name == "psycopg" else importlib.import_module(name),
    )
    with pytest.raises(ConfigError) as excinfo:
        make_repository(
            "postgres",
            str(tmp_path / "unused"),
            target_qq=1,
            postgres_dsn="postgresql://user:pass@127.0.0.1:5432/qqfetch",
        )
    assert "无法连接 PostgreSQL" in str(excinfo.value)
    assert "db=qqfetch" in str(excinfo.value)


def test_comment_key_prefers_comment_id():
    """评论有 comment_id 时应直接复用。"""
    comment = Comment(comment_id="c1", content="x", created_time=1, author_uin="2")
    assert _comment_key(1, "t1", comment) == "c1"


def test_comment_key_falls_back_to_digest():
    """评论缺少 comment_id 时应回退为稳定内容摘要。"""
    comment = Comment(comment_id="", content="x", created_time=1, author_uin="2")
    key = _comment_key(1, "t1", comment)
    assert len(key) == 40
