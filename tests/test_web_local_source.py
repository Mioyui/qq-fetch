"""本地 Web 数据源单测。"""

from __future__ import annotations

import json
import sqlite3

from qqfetch.web.sources.local_source import LocalSource


def _write_jsonl_target(root, qq: int, items) -> None:
    """写入一个 JSONL 目标目录。"""
    target = root / str(qq)
    target.mkdir(parents=True, exist_ok=True)
    with (target / "shuoshuo.jsonl").open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _write_sqlite_target(root, qq: int, items) -> None:
    """写入一个 SQLite 目标目录。"""
    target = root / str(qq)
    target.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target / "shuoshuo.sqlite")
    try:
        conn.execute(
            "CREATE TABLE shuoshuo (tid TEXT PRIMARY KEY, created_time INTEGER, content TEXT, data TEXT)"
        )
        for item in items:
            conn.execute(
                "INSERT INTO shuoshuo(tid, created_time, content, data) VALUES(?,?,?,?)",
                (item["tid"], item["created_time"], item["content"], json.dumps(item, ensure_ascii=False)),
            )
        conn.commit()
    finally:
        conn.close()


def _item(tid: str, created_time: int, *, comments=None):
    """构造本地结构化说说样本。"""
    return {
        "tid": tid,
        "content": "content-" + tid,
        "created_time": created_time,
        "like_count": 1,
        "comment_count": len(comments or []),
        "pictures": [{"pic_id": tid + "-p", "url": "https://example.com/" + tid + ".jpg", "width": 1, "height": 1}],
        "comments": comments or [],
        "raw": {"tid": tid},
    }


def test_local_source_lists_only_structured_targets(tmp_path):
    _write_jsonl_target(tmp_path, 10001, [_item("a", 10)])
    _write_sqlite_target(tmp_path, 10002, [_item("b", 20)])
    ghost = tmp_path / "10003"
    ghost.mkdir()
    (ghost / "checkpoint.json").write_text("{}", encoding="utf-8")

    source = LocalSource(str(tmp_path))
    friends = source.list_friends()
    assert [(item.target_qq, item.count) for item in friends] == [(10001, 1), (10002, 1)]


def test_local_source_sorts_filters_and_paginates(tmp_path):
    _write_jsonl_target(
        tmp_path,
        20001,
        [
            _item("a", 100),
            _item("b", 200),
            _item("c", 300),
        ],
    )
    source = LocalSource(str(tmp_path))

    items, total = source.list_shuoshuo(20001, page=1, page_size=2, sort="desc", start_ts=150, end_ts=350)
    assert total == 2
    assert [item.tid for item in items] == ["c", "b"]


def test_local_source_comments_are_independently_paginated(tmp_path):
    comments = [
        {"comment_id": "1", "content": "A", "created_time": 10, "author_uin": "u1", "author_name": "甲"},
        {"comment_id": "2", "content": "B", "created_time": 20, "author_uin": "u2", "author_name": "乙"},
    ]
    _write_sqlite_target(tmp_path, 30001, [_item("tid-1", 100, comments=comments)])
    source = LocalSource(str(tmp_path))

    items, total = source.list_comments(30001, "tid-1", page=1, page_size=1)
    assert total == 2
    assert len(items) == 1
    assert items[0].comment_id == "1"
