from __future__ import annotations

import json
import logging
from datetime import timedelta

import psycopg
from fb_crawl.parser import resolve_crawled_post_engagement
from fb_crawl.storage import _to_iso, _utcnow, comment_match_key, content_hash
from fb_crawl.types import Comment, Post
from psycopg.types.json import Jsonb

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)

_OWNER_ID_KEY = {"facebook_group": "group_id", "facebook_page": "page_id", "facebook_profile": "profile_id"}


class PgStorage:
    """Postgres-backed drop-in replacement for fb_crawl.storage.Storage.

    Scoped to a single crawl_targets row (one FB group or page). Injected into
    GroupCrawlService/PageCrawlService in place of the sqlite-backed Storage —
    those classes and fb_crawl.filters.classify_post only rely on this method
    surface (duck typing), so fb_crawl itself needs no changes.
    """

    def __init__(self, target_id: int, platform_type: str) -> None:
        if platform_type not in _OWNER_ID_KEY:
            raise ValueError(f"platform_type không hợp lệ cho FB storage: {platform_type}")
        self.target_id = target_id
        self.platform_type = platform_type
        self.pool = get_pool()

    # -- groups / pages (backed by crawl_targets) ------------------------

    def upsert_group(self, group_id: str, url: str, *, name: str | None = None) -> None:
        self._upsert_owner(group_id, url, name)

    def get_group(self, group_id: str) -> dict | None:
        return self._get_owner(group_id)

    def upsert_page(self, page_id: str, url: str, *, name: str | None = None) -> None:
        self._upsert_owner(page_id, url, name)

    def get_page(self, page_id: str) -> dict | None:
        return self._get_owner(page_id)

    def mark_group_synced(self, group_id: str) -> None:
        self._mark_synced()

    def mark_page_synced(self, page_id: str) -> None:
        self._mark_synced()

    def _upsert_owner(self, external_id: str, url: str, name: str | None) -> None:
        with self.pool.connection() as conn:
            try:
                with conn.transaction():
                    conn.execute(
                        """
                        UPDATE crawl_targets
                        SET external_id = %s,
                            url = %s,
                            -- display_name is user/import-controlled — the crawler
                            -- only fills it in when it's still unset (first crawl),
                            -- never overwrites an existing name. Previously this
                            -- re-wrote it from the live page on every single crawl,
                            -- so any extraction glitch (a verified-badge label, a
                            -- generic "All"/notification-count fallback, ...)
                            -- silently clobbered a correct, user-set name over and
                            -- over instead of just being a one-time bad read.
                            display_name = COALESCE(display_name, %s),
                            updated_at = now()
                        WHERE id = %s AND platform_type = %s
                        """,
                        (external_id, url, name, self.target_id, self.platform_type),
                    )
            except psycopg.errors.UniqueViolation:
                # This target's raw URL (e.g. profile.php?id=X) normalizes to
                # the same canonical URL another crawl_targets row already
                # owns (e.g. facebook.com/X, imported separately) — a true
                # duplicate of the same FB profile/page/group under two
                # target rows. Disable this one rather than let it fail the
                # same way on every future crawl forever; the surviving
                # duplicate keeps covering the same source.
                conn.execute(
                    "UPDATE crawl_targets SET enabled = false, last_error = %s, updated_at = now() WHERE id = %s",
                    (f"Trùng lặp với target khác đã có URL {url} — đã tự động tắt.", self.target_id),
                )
                logger.warning(
                    "Target %s (platform=%s) trùng URL chuẩn hoá %s với target khác — đã tắt.",
                    self.target_id,
                    self.platform_type,
                    url,
                )

    def _get_owner(self, external_id: str) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT external_id, display_name, url, last_crawled_at
                FROM crawl_targets
                WHERE id = %s AND platform_type = %s AND external_id = %s
                """,
                (self.target_id, self.platform_type, external_id),
            ).fetchone()
        if not row:
            return None
        return {
            _OWNER_ID_KEY[self.platform_type]: row["external_id"],
            "name": row["display_name"],
            "url": row["url"],
            "last_synced_at": _to_iso(row["last_crawled_at"]),
        }

    def _mark_synced(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE crawl_targets
                SET last_crawled_at = now(),
                    last_success_at = now(),
                    last_status = 'ok',
                    last_error = NULL,
                    consecutive_failures = 0,
                    updated_at = now()
                WHERE id = %s
                """,
                (self.target_id,),
            )

    # -- posts / comments (backed by documents / document_comments) -----

    def get_post(self, post_id: str) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT external_doc_id, owner_external_id, source_type, url, author,
                       content, content_hash, published_at, edited_at, is_edited,
                       images, videos, reaction_count, comment_count, like_count,
                       reactions, first_seen_at, last_seen_at
                FROM documents
                WHERE target_id = %s AND platform_type = %s AND external_doc_id = %s
                """,
                (self.target_id, self.platform_type, post_id),
            ).fetchone()
        if not row:
            return None
        return {
            "post_id": row["external_doc_id"],
            "group_id": row["owner_external_id"],
            "source_type": row["source_type"],
            "url": row["url"],
            "author": row["author"],
            "content": row["content"],
            "content_hash": row["content_hash"],
            "published_at": _to_iso(row["published_at"]),
            "edited_at": _to_iso(row["edited_at"]),
            "is_edited": int(bool(row["is_edited"])),
            "images_json": _dumps(row["images"] or []),
            "videos_json": _dumps(row["videos"] or []),
            "reaction_count": row["reaction_count"],
            "comment_count": row["comment_count"],
            "like_count": row["like_count"],
            "reactions_json": _dumps(row["reactions"] or {}),
            "first_seen_at": _to_iso(row["first_seen_at"]),
            "last_seen_at": _to_iso(row["last_seen_at"]),
        }

    def save_post(self, post: Post) -> None:
        eng = resolve_crawled_post_engagement(post.engagement, parsed_comment_count=len(post.comments))
        # Mirror fb_crawl.output._post_content: post.content often already
        # starts with the topic line, so only prepend it when it's actually
        # missing — otherwise the topic gets duplicated at the top.
        full_text = post.content
        if post.topic and post.topic not in (post.content or ""):
            full_text = f"{post.topic}\n\n{post.content}".strip() if post.content else post.topic
        owner_id = post.page_id if post.source_type in ("page", "profile") else post.group_id
        source_type = post.source_type or "group"
        post_content_hash = content_hash(full_text)

        with self.pool.connection() as conn:
            # Guards against the same real post being saved twice: either two
            # crawl_targets pointing at the same FB group/page (owner_external_id
            # matches, different target_id), or Facebook surfacing a different
            # pfbid for what's byte-identical content on a re-scrape. Scoped to
            # the owner (not global) so two different pages independently
            # posting the same boilerplate text isn't treated as a duplicate.
            duplicate = conn.execute(
                """
                SELECT id FROM documents
                WHERE owner_external_id = %(owner_id)s AND content_hash = %(content_hash)s
                  AND NOT (target_id = %(target_id)s AND external_doc_id = %(post_id)s)
                LIMIT 1
                """,
                {
                    "owner_id": owner_id,
                    "content_hash": post_content_hash,
                    "target_id": self.target_id,
                    "post_id": post.post_id,
                },
            ).fetchone()
            if duplicate is not None:
                return

            row = conn.execute(
                """
                INSERT INTO documents (
                    target_id, platform_type, source_type, external_doc_id, owner_external_id,
                    url, author, author_id, topic, content, content_hash,
                    published_at, edited_at, is_edited, images, videos,
                    like_count, comment_count, reaction_count, share_count, reactions
                ) VALUES (
                    %(target_id)s, %(platform_type)s, %(source_type)s, %(post_id)s, %(owner_id)s,
                    %(url)s, %(author)s, %(author_id)s, %(topic)s, %(content)s, %(content_hash)s,
                    %(published_at)s, %(edited_at)s, %(is_edited)s, %(images)s, %(videos)s,
                    %(like_count)s, %(comment_count)s, %(reaction_count)s, %(share_count)s, %(reactions)s
                )
                ON CONFLICT (target_id, external_doc_id) DO UPDATE SET
                    url = EXCLUDED.url,
                    author = EXCLUDED.author,
                    author_id = EXCLUDED.author_id,
                    topic = EXCLUDED.topic,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    published_at = COALESCE(EXCLUDED.published_at, documents.published_at),
                    edited_at = COALESCE(EXCLUDED.edited_at, documents.edited_at),
                    is_edited = documents.is_edited OR EXCLUDED.is_edited,
                    images = EXCLUDED.images,
                    videos = EXCLUDED.videos,
                    like_count = EXCLUDED.like_count,
                    comment_count = EXCLUDED.comment_count,
                    reaction_count = EXCLUDED.reaction_count,
                    share_count = EXCLUDED.share_count,
                    reactions = EXCLUDED.reactions,
                    last_seen_at = now()
                RETURNING id
                """,
                {
                    "target_id": self.target_id,
                    "platform_type": self.platform_type,
                    "source_type": source_type,
                    "post_id": post.post_id,
                    "owner_id": owner_id,
                    "url": post.url,
                    "author": post.author,
                    "author_id": post.author_id,
                    "topic": post.topic,
                    "content": full_text,
                    "content_hash": post_content_hash,
                    "published_at": post.published_at,
                    "edited_at": post.edited_at,
                    "is_edited": bool(post.is_edited),
                    "images": Jsonb(post.images or []),
                    "videos": Jsonb(post.videos or []),
                    "like_count": eng.like_count,
                    "comment_count": eng.comment_count,
                    "reaction_count": eng.reaction_count,
                    "share_count": eng.share_count,
                    "reactions": Jsonb(eng.reactions or {}),
                },
            ).fetchone()
            conn.execute(
                """
                INSERT INTO document_engagement_snapshots
                    (document_id, like_count, comment_count, reaction_count, share_count)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (row["id"], eng.like_count, eng.comment_count, eng.reaction_count, eng.share_count),
            )

    def update_extra(self, post_id: str, extra: dict) -> None:
        """Merge extra crawl-cycle metadata (filter_reason, is_first_crawl...)
        into documents.extra — not part of fb_crawl's Storage interface, so
        callers (facebook_runner) invoke this directly, not via classify_post."""
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE documents SET extra = extra || %s::jsonb
                WHERE target_id = %s AND platform_type = %s AND external_doc_id = %s
                """,
                (Jsonb(extra), self.target_id, self.platform_type, post_id),
            )

    def upsert_comments(self, post_id: str, comments: list[Comment]) -> list[Comment]:
        new_comments: list[Comment] = []
        with self.pool.connection() as conn:
            doc = conn.execute(
                "SELECT id FROM documents WHERE target_id = %s AND platform_type = %s AND external_doc_id = %s",
                (self.target_id, self.platform_type, post_id),
            ).fetchone()
            if not doc:
                return new_comments
            document_id = doc["id"]

            existing_rows = conn.execute(
                "SELECT external_comment_id, match_key, content_hash FROM document_comments WHERE document_id = %s",
                (document_id,),
            ).fetchall()
            # match_key (author|parent|depth) only identifies "same slot as a
            # previously stored comment" for edit detection — it collides when
            # one author posts multiple distinct top-level comments. Each
            # existing row may be claimed as an edit-match at most once per
            # batch (via pop); anything left unclaimed falls through to a
            # plain insert instead of silently overwriting an unrelated
            # comment's text.
            by_match = {r["match_key"]: r for r in existing_rows}
            seen_ids = {r["external_comment_id"] for r in existing_rows}

            for comment in comments:
                if comment.comment_id in seen_ids:
                    continue  # unchanged content, already stored

                key = comment_match_key(comment)
                row = by_match.pop(key, None)
                if row is not None:
                    if row["content_hash"] != content_hash(comment.text):
                        conn.execute(
                            """
                            UPDATE document_comments
                            SET text = %s, content_hash = %s, created_at = COALESCE(%s, created_at), is_edited = TRUE
                            WHERE document_id = %s AND external_comment_id = %s
                            """,
                            (
                                comment.text,
                                content_hash(comment.text),
                                comment.created_at,
                                document_id,
                                row["external_comment_id"],
                            ),
                        )
                    seen_ids.add(comment.comment_id)
                    continue

                inserted = conn.execute(
                    """
                    INSERT INTO document_comments (
                        document_id, external_comment_id, author, author_id, text,
                        content_hash, parent_comment_id, depth, match_key, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_id, external_comment_id) DO NOTHING
                    RETURNING external_comment_id
                    """,
                    (
                        document_id,
                        comment.comment_id,
                        comment.author,
                        comment.author_id,
                        comment.text,
                        content_hash(comment.text),
                        comment.parent_comment_id,
                        comment.depth,
                        key,
                        comment.created_at,
                    ),
                ).fetchone()
                if inserted is None:
                    continue
                seen_ids.add(comment.comment_id)
                # Deliberately not re-added to by_match: doing so would let a
                # later comment in this same batch "claim" this brand-new row
                # as an edit target, reintroducing the same collision bug for
                # same-batch duplicates (e.g. several new same-author comments
                # arriving in one crawl).
                new_comments.append(comment)

        return new_comments

    def list_posts_to_recheck(
        self,
        owner_id: str,
        *,
        since_hours: float = 48,
        source_type: str = "group",
    ) -> list[dict]:
        since = _utcnow() - timedelta(hours=since_hours)
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT external_doc_id AS post_id, url
                FROM documents
                WHERE target_id = %s AND platform_type = %s AND owner_external_id = %s AND source_type = %s
                  AND comment_count > 0
                  AND (
                      published_at >= %s
                      OR (published_at IS NULL AND first_seen_at >= %s)
                  )
                ORDER BY last_seen_at DESC
                LIMIT 25
                """,
                (self.target_id, self.platform_type, owner_id, source_type, since, since),
            ).fetchall()
        return list(rows)

    def known_post_ids(self, owner_id: str, *, source_type: str) -> set[str]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT external_doc_id FROM documents
                WHERE target_id = %s AND platform_type = %s AND owner_external_id = %s AND source_type = %s
                """,
                (self.target_id, self.platform_type, owner_id, source_type),
            ).fetchall()
        return {r["external_doc_id"] for r in rows}

    def known_comment_ids(self, post_id: str) -> set[str]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT dc.external_comment_id
                FROM document_comments dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.target_id = %s AND d.platform_type = %s AND d.external_doc_id = %s
                """,
                (self.target_id, self.platform_type, post_id),
            ).fetchall()
        return {r["external_comment_id"] for r in rows}


def _dumps(value: list | dict) -> str:
    return json.dumps(value, ensure_ascii=False)
