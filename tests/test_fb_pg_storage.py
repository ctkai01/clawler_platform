from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fb_crawl.types import Comment, Post, PostEngagement

from platform_app.adapters.fb_pg_storage import PgStorage
from platform_app.db.pool import get_pool


@pytest.fixture
def target_id() -> int:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            DELETE FROM documents
            WHERE target_id IN (SELECT id FROM crawl_targets WHERE url = %s)
            """,
            ("https://facebook.com/groups/test123",),
        )
        conn.execute("DELETE FROM crawl_targets WHERE url = %s", ("https://facebook.com/groups/test123",))
        row = conn.execute(
            """
            INSERT INTO crawl_targets (platform_type, url, display_name, enabled)
            VALUES ('facebook_group', 'https://facebook.com/groups/test123', 'seed', false)
            RETURNING id
            """
        ).fetchone()
    return row["id"]


@pytest.fixture
def storage(target_id: int) -> PgStorage:
    return PgStorage(target_id=target_id, platform_type="facebook_group")


def _make_post(post_id: str = "post_1", *, comments: list[Comment] | None = None) -> Post:
    return Post(
        post_id=post_id,
        group_id="group_123",
        url=f"https://facebook.com/groups/test123/posts/{post_id}",
        author="Nguyen Van A",
        topic="Hello",
        content="Nội dung bài viết test",
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
        engagement=PostEngagement(like_count=5, reaction_count=5, comment_count=2),
        source_type="group",
        comments=comments or [],
    )


def test_upsert_group_and_get_group(storage: PgStorage) -> None:
    storage.upsert_group("group_123", "https://facebook.com/groups/test123", name="Test Group")
    row = storage.get_group("group_123")
    assert row is not None
    assert row["group_id"] == "group_123"
    assert row["name"] == "Test Group"

    assert storage.get_group("does_not_exist") is None


def test_save_post_roundtrip_and_update(storage: PgStorage) -> None:
    storage.upsert_group("group_123", "https://facebook.com/groups/test123")
    post = _make_post()

    assert storage.get_post(post.post_id) is None

    storage.save_post(post)
    row = storage.get_post(post.post_id)
    assert row is not None
    assert row["post_id"] == "post_1"
    assert row["group_id"] == "group_123"
    assert row["like_count"] == 5
    assert row["first_seen_at"] is not None

    first_seen = row["first_seen_at"]

    post.content = "Nội dung đã chỉnh sửa"
    post.is_edited = True
    storage.save_post(post)
    updated = storage.get_post(post.post_id)
    assert updated is not None
    assert updated["content"].endswith("Nội dung đã chỉnh sửa")
    assert updated["is_edited"] == 1
    assert updated["first_seen_at"] == first_seen  # first_seen_at must not move on update


def test_update_extra_merges_without_clobbering(storage: PgStorage) -> None:
    storage.upsert_group("group_123", "https://facebook.com/groups/test123")
    post = _make_post()
    storage.save_post(post)

    storage.update_extra(post.post_id, {"filter_reason": "new_post", "is_first_crawl": True})
    row = storage.get_post(post.post_id)
    assert row is not None

    pool = get_pool()
    with pool.connection() as conn:
        extra = conn.execute(
            "SELECT extra FROM documents WHERE platform_type='facebook_group' AND external_doc_id=%s",
            (post.post_id,),
        ).fetchone()["extra"]
    assert extra == {"filter_reason": "new_post", "is_first_crawl": True}

    storage.update_extra(post.post_id, {"filter_reason": "recent_comments"})
    with pool.connection() as conn:
        extra = conn.execute(
            "SELECT extra FROM documents WHERE platform_type='facebook_group' AND external_doc_id=%s",
            (post.post_id,),
        ).fetchone()["extra"]
    assert extra == {"filter_reason": "recent_comments", "is_first_crawl": True}


def test_upsert_comments_dedupes_and_updates_edits(storage: PgStorage) -> None:
    storage.upsert_group("group_123", "https://facebook.com/groups/test123")
    post = _make_post()
    storage.save_post(post)

    c1 = Comment(comment_id="c1", author="Author A", text="Bình luận 1")
    c2 = Comment(comment_id="c2", author="Author B", text="Bình luận 2")
    new_comments = storage.upsert_comments(post.post_id, [c1, c2])
    assert {c.comment_id for c in new_comments} == {"c1", "c2"}
    assert storage.known_comment_ids(post.post_id) == {"c1", "c2"}

    # Re-submitting the same comments must not create duplicates.
    again = storage.upsert_comments(post.post_id, [c1, c2])
    assert again == []
    assert storage.known_comment_ids(post.post_id) == {"c1", "c2"}

    # Same author/parent/depth but different comment_id (as real edits are —
    # comment_id is content-derived, so edited text means a new id) -> content
    # update via match_key, not a new row.
    c1_edited = Comment(comment_id="c1-edited", author="Author A", text="Bình luận 1 (đã sửa)")
    edited_result = storage.upsert_comments(post.post_id, [c1_edited])
    assert edited_result == []
    assert storage.known_comment_ids(post.post_id) == {"c1", "c2"}


def test_upsert_comments_same_author_multiple_new_comments_not_collapsed(storage: PgStorage) -> None:
    """Regression test: 3 distinct top-level comments from the same author
    (same match_key: author|no-parent|depth=0) must all be stored, not
    collapsed into one via match_key collision."""
    storage.upsert_group("group_123", "https://facebook.com/groups/test123")
    post = _make_post()
    storage.save_post(post)

    comments = [
        Comment(comment_id="a1", author="Avin Tran", text="IB Anh Nhé"),
        Comment(comment_id="a2", author="Avin Tran", text="Anh Bên Vinaphone Đây"),
        Comment(comment_id="a3", author="Avin Tran", text="Anh Chỉ Cho"),
    ]
    new_comments = storage.upsert_comments(post.post_id, comments)
    assert {c.comment_id for c in new_comments} == {"a1", "a2", "a3"}
    assert storage.known_comment_ids(post.post_id) == {"a1", "a2", "a3"}


def test_list_posts_to_recheck(storage: PgStorage) -> None:
    storage.upsert_group("group_123", "https://facebook.com/groups/test123")
    post = _make_post()
    storage.save_post(post)
    storage.upsert_comments(post.post_id, [Comment(comment_id="c1", author="A", text="hi")])
    # comment_count only reflects what save_post recorded (parsed_comment_count), so re-save
    # after adding a comment to keep comment_count > 0 for the recheck query.
    post.comments = [Comment(comment_id="c1", author="A", text="hi")]
    storage.save_post(post)

    due = storage.list_posts_to_recheck("group_123", since_hours=48, source_type="group")
    assert any(r["post_id"] == post.post_id for r in due)


def test_mark_group_synced_updates_target(storage: PgStorage, target_id: int) -> None:
    storage.upsert_group("group_123", "https://facebook.com/groups/test123")
    storage.mark_group_synced("group_123")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT last_status, last_crawled_at FROM crawl_targets WHERE id = %s", (target_id,)
        ).fetchone()
    assert row["last_status"] == "ok"
    assert row["last_crawled_at"] is not None
