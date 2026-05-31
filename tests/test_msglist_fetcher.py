"""MsglistFetcher 单测:分页聚合、按 total 终止、max_count、断点续传、跨页去重。

用 FakeClient 注入预设页,不触网。
"""

from __future__ import annotations

from qqfetch.qzone.msglist import MsglistFetcher
from qqfetch.storage.checkpoint import Checkpoint
from qqfetch.storage.repository import JsonlRepository


class FakeClient:
    """按 pos 返回预设页的假客户端。"""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def call_msglist(self, host_uin, pos, num):
        self.calls.append((host_uin, pos, num))
        return self.pages.get(pos, {"code": 0, "total": 0, "msglist": []})


def _payload(tids, total):
    return {
        "code": 0,
        "total": total,
        "msglist": [{"tid": t, "content": t, "created_time": 1} for t in tids],
    }


def _fetcher(pages, tmp_path, **kw):
    repo = JsonlRepository(str(tmp_path / "d.jsonl"))
    cp = Checkpoint.load(tmp_path / "cp.json")
    return MsglistFetcher(FakeClient(pages), repo, cp, **kw), repo


def test_paginates_and_collects_all(tmp_path):
    pages = {0: _payload(["a", "b"], 4), 2: _payload(["c", "d"], 4)}
    f, repo = _fetcher(pages, tmp_path, page_size=2)
    assert [s.tid for s in f.fetch_all(123)] == ["a", "b", "c", "d"]
    assert repo.count() == 4


def test_stops_at_total(tmp_path):
    pages = {0: _payload(["a", "b"], 2)}
    f, _ = _fetcher(pages, tmp_path, page_size=2)
    assert [s.tid for s in f.fetch_all(123)] == ["a", "b"]


def test_max_count(tmp_path):
    pages = {0: _payload(["a", "b", "c", "d"], 10)}
    f, _ = _fetcher(pages, tmp_path, page_size=4, max_count=2)
    assert [s.tid for s in f.fetch_all(123)] == ["a", "b"]


def test_resume_from_checkpoint(tmp_path):
    pages = {0: _payload(["a", "b"], 4), 2: _payload(["c", "d"], 4)}
    Checkpoint.load(tmp_path / "cp.json").advance(2, ["a", "b"])  # 预置:已到 pos=2,已见 a,b
    repo = JsonlRepository(str(tmp_path / "d.jsonl"))
    f = MsglistFetcher(FakeClient(pages), repo, Checkpoint.load(tmp_path / "cp.json"), page_size=2)
    assert [s.tid for s in f.fetch_all(123)] == ["c", "d"]        # 续抓,不重复 a,b


def test_dedup_across_overlapping_pages(tmp_path):
    pages = {0: _payload(["a", "b"], 4), 2: _payload(["b", "c"], 4), 4: _payload([], 4)}
    f, repo = _fetcher(pages, tmp_path, page_size=2)
    assert [s.tid for s in f.fetch_all(123)] == ["a", "b", "c"]   # 重叠的 b 被去重
    assert repo.count() == 3
