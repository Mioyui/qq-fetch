"""PostgreSQL 集成测试:仅在提供测试库 DSN 时运行。"""

from __future__ import annotations

import os
import uuid

import pytest

from qqfetch.models import Comment, Picture, Shuoshuo
from qqfetch.storage.repository import PostgresRepository

pytestmark = pytest.mark.skipif(
    not os.getenv("QQFETCH_TEST_POSTGRES_DSN"),
    reason="未提供 QQFETCH_TEST_POSTGRES_DSN，跳过 PostgreSQL 集成测试",
)


def _sh(*, tid: str, content: str, like_count: int, comment_suffix: str) -> Shuoshuo:
    """构造一条带评论和图片的说说快照。"""
    return Shuoshuo(
        tid=tid,
        content=content,
        created_time=100,
        like_count=like_count,
        comment_count=1,
        pictures=[Picture(pic_id="p1", url="https://example.com/1.jpg", width=1, height=2)],
        comments=[
            Comment(
                comment_id="",
                content="reply-" + comment_suffix,
                created_time=101,
                author_uin="20001",
                author_name="tester",
            )
        ],
        raw={"tid": tid, "content": content, "like_count": like_count},
    )


def test_postgres_save_upsert_and_replace_children():
    """同一 tid 二次保存时应更新主表并替换评论/图片快照。"""
    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ["QQFETCH_TEST_POSTGRES_DSN"]
    schema = "qqfetch_" + uuid.uuid4().hex[:12]
    repo = PostgresRepository(dsn, target_qq=123456, schema=schema, auto_init=True)
    try:
        assert repo.save(_sh(tid="t1", content="first", like_count=1, comment_suffix="a")) is True
        assert repo.save(_sh(tid="t1", content="second", like_count=2, comment_suffix="b")) is False
        assert repo.count() == 1

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT content, like_count FROM "{schema}".qqfetch_shuoshuo '
                    "WHERE target_qq=%s AND tid=%s",
                    (123456, "t1"),
                )
                assert cur.fetchone() == ("second", 2)

                cur.execute(
                    f'SELECT content FROM "{schema}".qqfetch_comment '
                    "WHERE target_qq=%s AND tid=%s",
                    (123456, "t1"),
                )
                assert cur.fetchall() == [("reply-b",)]

                cur.execute(
                    f'SELECT pic_id, sort_index FROM "{schema}".qqfetch_picture '
                    "WHERE target_qq=%s AND tid=%s",
                    (123456, "t1"),
                )
                assert cur.fetchall() == [("p1", 0)]
    finally:
        repo.close()
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
