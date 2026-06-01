"""MsglistFetcher 单测:分页、断点续传、去重，以及 save() 语义。"""

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


class RecordingRepo:
    """只记录 save() 调用结果的假仓储。"""

    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.saved = []

    def save(self, sh):
        self.saved.append(sh.tid)
        if sh.tid in self.existing:
            return False
        self.existing.add(sh.tid)
        return True

    def count(self):
        return len(self.existing)

    def close(self):
        pass


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
    Checkpoint.load(tmp_path / "cp.json").advance(2, ["a", "b"])
    repo = JsonlRepository(str(tmp_path / "d.jsonl"))
    f = MsglistFetcher(FakeClient(pages), repo, Checkpoint.load(tmp_path / "cp.json"), page_size=2)
    assert [s.tid for s in f.fetch_all(123)] == ["c", "d"]


def test_dedup_across_overlapping_pages(tmp_path):
    pages = {0: _payload(["a", "b"], 4), 2: _payload(["b", "c"], 4), 4: _payload([], 4)}
    f, repo = _fetcher(pages, tmp_path, page_size=2)
    assert [s.tid for s in f.fetch_all(123)] == ["a", "b", "c"]
    assert repo.count() == 3


def test_existing_repo_item_is_still_saved_for_refresh(tmp_path):
    """仓储返回 False 时不计新增，但 fetcher 仍应调用 save() 以支持快照刷新。"""
    pages = {0: _payload(["a", "b"], 2)}
    repo = RecordingRepo(existing={"a"})
    cp = Checkpoint.load(tmp_path / "cp.json")
    fetcher = MsglistFetcher(FakeClient(pages), repo, cp, page_size=2)
    assert [s.tid for s in fetcher.fetch_all(123)] == ["b"]
    assert repo.saved == ["a", "b"]
