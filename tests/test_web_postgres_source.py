"""PostgreSQL Web 数据源集成测试。"""

from __future__ import annotations

import os
import uuid

import pytest

from qqfetch.models import Comment, Picture, Shuoshuo
from qqfetch.storage.repository import PostgresRepository
from qqfetch.web.sources.postgres_source import PostgresSource

pytestmark = pytest.mark.skipif(
    not os.getenv("QQFETCH_TEST_POSTGRES_DSN"),
    reason="未提供 QQFETCH_TEST_POSTGRES_DSN，跳过 PostgreSQL Web 数据源测试",
)


def _sh(tid: str, created_time: int, *, content: str) -> Shuoshuo:
    """构造 PostgreSQL 集成测试用样本。"""
    return Shuoshuo(
        tid=tid,
        content=content,
        created_time=created_time,
        like_count=2,
        comment_count=1,
        pictures=[Picture(pic_id=tid + "-p", url="https://example.com/" + tid + ".jpg", width=10, height=20)],
        comments=[Comment(comment_id="1", content="reply-" + tid, created_time=created_time + 1, author_uin="u1", author_name="甲")],
        raw={"tid": tid, "content": content},
    )


def test_postgres_source_lists_friends_and_paginates():
    dsn = os.environ["QQFETCH_TEST_POSTGRES_DSN"]
    schema = "web_" + uuid.uuid4().hex[:10]
    repo = PostgresRepository(dsn, target_qq=7654321, schema=schema, auto_init=True)
    try:
        repo.save(_sh("a", 100, content="first"))
        repo.save(_sh("b", 200, content="second"))
        source = PostgresSource(dsn, schema)

        friends = source.list_friends()
        assert friends[0].target_qq == 7654321

        items, total = source.list_shuoshuo(7654321, page=1, page_size=1, sort="desc", start_ts=None, end_ts=None)
        assert total == 2
        assert items[0].tid == "b"
        assert items[0].pictures[0].pic_id == "b-p"

        comments, comment_total = source.list_comments(7654321, "a", page=1, page_size=10)
        assert comment_total == 1
        assert comments[0].content == "reply-a"
    finally:
        repo.close()
        psycopg = pytest.importorskip("psycopg")
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
