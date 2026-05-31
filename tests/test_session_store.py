"""SessionStore 单测:存取往返、缺失、损坏、清除。"""

from __future__ import annotations

from qqfetch.auth.session_store import SavedSession, SessionStore


def test_save_load_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "s.json")
    sess = SavedSession(cookies={"p_skey": "k", "uin": "o123"}, uin=123, nickname="昵称")
    store.save(sess)
    loaded = store.load()
    assert loaded is not None
    assert loaded.cookies == {"p_skey": "k", "uin": "o123"}
    assert loaded.uin == 123
    assert loaded.nickname == "昵称"


def test_load_missing_returns_none(tmp_path):
    assert SessionStore(tmp_path / "none.json").load() is None


def test_load_corrupt_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ 这不是合法 json", encoding="utf-8")
    assert SessionStore(p).load() is None


def test_clear_is_idempotent(tmp_path):
    store = SessionStore(tmp_path / "c.json")
    store.save(SavedSession(cookies={}, uin=1))
    store.clear()
    assert store.load() is None
    store.clear()  # 再次清除不应报错
