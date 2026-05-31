"""Checkpoint 单测:初始态、推进、持久化往返、重置、损坏兜底。"""

from __future__ import annotations

from qqfetch.storage.checkpoint import Checkpoint


def test_initial_state(tmp_path):
    cp = Checkpoint.load(tmp_path / "cp.json")
    assert cp.pos == 0 and cp.seen_tids == set()


def test_advance_and_seen(tmp_path):
    cp = Checkpoint.load(tmp_path / "cp.json")
    cp.advance(20, ["a", "b"])
    assert cp.pos == 20
    assert cp.seen("a") and cp.seen("b") and not cp.seen("c")


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "cp.json"
    Checkpoint.load(p).advance(40, ["x", "y"])
    cp2 = Checkpoint.load(p)
    assert cp2.pos == 40 and cp2.seen("x") and cp2.seen("y")


def test_reset(tmp_path):
    p = tmp_path / "cp.json"
    cp = Checkpoint.load(p)
    cp.advance(10, ["a"])
    cp.reset()
    assert cp.pos == 0 and not cp.seen("a")
    assert Checkpoint.load(p).pos == 0


def test_corrupt_file_starts_fresh(tmp_path):
    p = tmp_path / "cp.json"
    p.write_text("不是合法 json", encoding="utf-8")
    assert Checkpoint.load(p).pos == 0
