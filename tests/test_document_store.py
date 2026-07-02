from __future__ import annotations

from datetime import datetime, timezone

import pytest

from platform_app.adapters.document_store import save_document
from platform_app.db.pool import get_pool
from platform_app.parsers.base import ParsedComment, ParsedDocument


@pytest.fixture
def target_id() -> int:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            DELETE FROM documents
            WHERE target_id IN (SELECT id FROM crawl_targets WHERE url = %s)
            """,
            ("https://forum.example.com/board",),
        )
        conn.execute("DELETE FROM crawl_targets WHERE url = %s", ("https://forum.example.com/board",))
        row = conn.execute(
            """
            INSERT INTO crawl_targets (platform_type, url, parser_key, enabled)
            VALUES ('forum', 'https://forum.example.com/board', 'generic_css', false)
            RETURNING id
            """
        ).fetchone()
    return row["id"]


def test_save_document_roundtrip_and_update(target_id: int) -> None:
    doc = ParsedDocument(
        external_doc_id="forum.example.com:/t/hello-world",
        url="https://forum.example.com/t/hello-world",
        author="alice",
        topic="Hello world",
        content="Nội dung ban đầu",
        published_at=datetime.now(timezone.utc),
        comments=[
            ParsedComment(external_comment_id="c1", author="bob", text="Bình luận 1"),
            ParsedComment(external_comment_id="c2", author="carol", text="Bình luận 2"),
        ],
    )
    save_document(target_id, "forum", "forum_thread", None, doc)

    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE platform_type='forum' AND external_doc_id=%s",
            (doc.external_doc_id,),
        ).fetchone()
        assert row is not None
        assert row["content"] == "Nội dung ban đầu"
        assert row["comment_count"] == 2

        comments = conn.execute(
            "SELECT external_comment_id, text FROM document_comments WHERE document_id = %s ORDER BY external_comment_id",
            (row["id"],),
        ).fetchall()
        assert [c["text"] for c in comments] == ["Bình luận 1", "Bình luận 2"]

    doc.content = "Nội dung đã chỉnh sửa"
    save_document(target_id, "forum", "forum_thread", None, doc)
    with pool.connection() as conn:
        updated = conn.execute(
            "SELECT content, is_edited FROM documents WHERE platform_type='forum' AND external_doc_id=%s",
            (doc.external_doc_id,),
        ).fetchone()
    assert updated["content"] == "Nội dung đã chỉnh sửa"
    assert updated["is_edited"] is True
