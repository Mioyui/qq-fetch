"""image_urls 单测:原图选取、字段兜底、URL 规范化、去重键。"""

from __future__ import annotations

from qqfetch.qzone.image_urls import extract_pictures, to_original_url


def test_prefer_original_picks_url3():
    item = {"pic": [{"pic_id": "P", "url1": "http://a/s.jpg",
                     "url2": "http://a/m.jpg", "url3": "http://a/l.jpg"}]}
    pics = extract_pictures(item, prefer_original=True)
    assert len(pics) == 1
    assert pics[0].url == "https://a/l.jpg"   # url3 优先 + http->https 规范化
    assert pics[0].pic_id == "P"


def test_prefer_small_picks_url1():
    item = {"pic": [{"url1": "http://a/s.jpg", "url3": "http://a/l.jpg"}]}
    pics = extract_pictures(item, prefer_original=False)
    assert pics[0].url == "https://a/s.jpg"


def test_pic_id_falls_back_to_hash():
    pics = extract_pictures({"pic": [{"url1": "http://a/x.jpg"}]})
    assert len(pics[0].pic_id) == 16          # sha1 短哈希


def test_protocol_relative_url():
    assert to_original_url({"url3": "//cdn/x.jpg"}) == "https://cdn/x.jpg"


def test_escaped_slashes_and_amp():
    out = to_original_url({"url3": "http:\\/\\/a.com\\/p.jpg?a=1&amp;b=2"})
    assert out == "https://a.com/p.jpg?a=1&b=2"


def test_no_pic_returns_empty():
    assert extract_pictures({}) == []


def test_dedup_key_prefers_pic_id():
    p = extract_pictures({"pic": [{"pic_id": "P", "url1": "http://a/x.jpg"}]})[0]
    assert p.dedup_key() == "P"
