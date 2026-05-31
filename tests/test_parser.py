"""parser 单测:基于构造样例 fixture(待探测脚本用真实数据替换)。"""

from __future__ import annotations

import json
from pathlib import Path

from qqfetch.qzone.parser import parse_msglist

_FIX = Path(__file__).parent / "fixtures" / "msglist_sample.json"


def _load():
    return json.loads(_FIX.read_text(encoding="utf-8"))


def test_count_and_total():
    page = parse_msglist(_load())
    assert page.total == 2
    assert len(page.items) == 2


def test_first_shuoshuo_fields():
    s = parse_msglist(_load()).items[0]
    assert s.tid == "abc123"
    assert s.content == "今天天气不错,出去走走"
    assert s.created_time == 1600000000
    assert s.comment_count == 1
    assert len(s.pictures) == 1
    assert len(s.comments) == 1
    assert s.comments[0].author_name == "张三"
    assert s.comments[0].created_time == 1600000100


def test_time_field_falls_back_to_abstime():
    s = parse_msglist(_load()).items[1]
    assert s.created_time == 1600000200   # 无 created_time 时用 abstime
    assert s.pictures == []
    assert s.comments == []


def test_raw_preserved():
    s = parse_msglist(_load()).items[0]
    assert s.raw["tid"] == "abc123"       # 原始 JSON 完整保留


def test_empty_payload():
    page = parse_msglist({})
    assert page.items == [] and page.total == 0
