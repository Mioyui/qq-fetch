"""Web API 与页面入口单测。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from qqfetch.web.app import create_app


def _write_jsonl_target(root, qq: int, items) -> None:
    """写入一个 JSONL 目标目录。"""
    target = root / str(qq)
    target.mkdir(parents=True, exist_ok=True)
    with (target / "shuoshuo.jsonl").open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _make_config(tmp_path, data_dir: str, *, postgres_dsn: str = ""):
    """生成最小配置文件。"""
    config = tmp_path / "config.toml"
    normalized_data_dir = data_dir.replace("\\", "/")
    config.write_text(
        "\n".join(
            [
                "[storage]",
                f'data_dir = "{normalized_data_dir}"',
                f'postgres_dsn = "{postgres_dsn}"',
                'postgres_schema = "public"',
            ]
        ),
        encoding="utf-8",
    )
    return config


def _item(tid: str, created_time: int):
    """构造 API 样本数据。"""
    return {
        "tid": tid,
        "content": "content-" + tid,
        "created_time": created_time,
        "like_count": 1,
        "comment_count": 1,
        "pictures": [{"pic_id": tid + "-p", "url": "https://example.com/" + tid + ".jpg", "width": 1, "height": 1}],
        "comments": [{"comment_id": tid + "-c", "content": "reply", "created_time": created_time + 1, "author_uin": "u1", "author_name": "甲"}],
        "raw": {"tid": tid},
    }


def test_web_page_and_local_api(tmp_path):
    data_dir = tmp_path / "data"
    _write_jsonl_target(data_dir, 123456, [_item("a", 100), _item("b", 200)])
    client = TestClient(create_app(str(_make_config(tmp_path, str(data_dir)))))

    page = client.get("/")
    assert page.status_code == 200
    assert "qqfetch" in page.text

    friends = client.get("/api/friends", params={"source": "local"})
    assert friends.status_code == 200
    assert friends.json()["items"][0]["target_qq"] == 123456

    shuoshuo = client.get(
        "/api/shuoshuo",
        params={"source": "local", "target_qq": 123456, "page": 1, "page_size": 1, "sort": "desc", "preset": "all"},
    )
    assert shuoshuo.status_code == 200
    assert shuoshuo.json()["total"] == 2
    assert shuoshuo.json()["items"][0]["tid"] == "b"

    comments = client.get(
        "/api/comments",
        params={"source": "local", "target_qq": 123456, "tid": "a", "page": 1, "page_size": 10},
    )
    assert comments.status_code == 200
    assert comments.json()["items"][0]["comment_id"] == "a-c"


def test_postgres_source_without_dsn_returns_clear_error(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client = TestClient(create_app(str(_make_config(tmp_path, str(data_dir)))))
    resp = client.get("/api/friends", params={"source": "postgres"})
    assert resp.status_code == 400
    assert "postgres_dsn" in resp.json()["detail"]
