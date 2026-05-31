"""Repository 单测:JSONL 与 SQLite 的增删查与去重、JSONL 索引重载。"""

from __future__ import annotations

import pytest

from qqfetch.models import Shuoshuo
from qqfetch.storage.repository import JsonlRepository, make_repository


def _sh(tid):
    return Shuoshuo(tid=tid, content="c" + tid, created_time=100)


@pytest.mark.parametrize("fmt", ["jsonl", "sqlite"])
def test_append_exists_count_dedup(tmp_path, fmt):
    repo = make_repository(fmt, str(tmp_path / ("d." + fmt)))
    assert not repo.exists("t1")
    repo.append(_sh("t1"))
    assert repo.exists("t1") and repo.count() == 1
    repo.append(_sh("t1"))            # 同 tid 去重,不增加
    assert repo.count() == 1
    repo.append(_sh("t2"))
    assert repo.count() == 2
    repo.close()


def test_jsonl_reload_index(tmp_path):
    p = str(tmp_path / "d.jsonl")
    r1 = JsonlRepository(p)
    r1.append(_sh("a"))
    r1.append(_sh("b"))
    r2 = JsonlRepository(p)           # 重新加载应识别已存 tid
    assert r2.exists("a") and r2.exists("b") and r2.count() == 2
