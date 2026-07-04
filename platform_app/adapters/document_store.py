from __future__ import annotations

import hashlib

from psycopg.types.json import Jsonb

from platform_app.db.pool import get_pool
from platform_app.parsers.base import ParsedDocument


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def save_document(
    target_id: int,
    platform_type: str,
    source_type: str,
    owner_external_id: str | None,
    doc: ParsedDocument,
) -> None:
    """Upsert a forum thread / news article (and its comments) into the shared
    documents/document_comments tables — the same tables PgStorage writes FB
    posts into, but without any fb_crawl dependency."""

    with get_pool().connection() as conn:
        row = conn.execute(
            """
            INSERT INTO documents (
                target_id, platform_type, source_type, external_doc_id, owner_external_id,
                url, author, topic, content, content_hash,
                published_at, edited_at, images, videos, extra, comment_count
            ) VALUES (
                %(target_id)s, %(platform_type)s, %(source_type)s, %(external_doc_id)s, %(owner_external_id)s,
                %(url)s, %(author)s, %(topic)s, %(content)s, %(content_hash)s,
                %(published_at)s, %(edited_at)s, %(images)s, %(videos)s, %(extra)s, %(comment_count)s
            )
            ON CONFLICT (target_id, external_doc_id) DO UPDATE SET
                url = EXCLUDED.url,
                author = EXCLUDED.author,
                topic = EXCLUDED.topic,
                content = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                published_at = COALESCE(EXCLUDED.published_at, documents.published_at),
                edited_at = COALESCE(EXCLUDED.edited_at, documents.edited_at),
                is_edited = documents.is_edited OR (documents.content_hash <> EXCLUDED.content_hash),
                images = EXCLUDED.images,
                videos = EXCLUDED.videos,
                extra = EXCLUDED.extra,
                comment_count = EXCLUDED.comment_count,
                last_seen_at = now()
            RETURNING id
            """,
            {
                "target_id": target_id,
                "platform_type": platform_type,
                "source_type": source_type,
                "external_doc_id": doc.external_doc_id,
                "owner_external_id": owner_external_id,
                "url": doc.url,
                "author": doc.author,
                "topic": doc.topic,
                "content": doc.content,
                "content_hash": _content_hash(doc.content),
                "published_at": doc.published_at,
                "edited_at": doc.edited_at,
                "images": Jsonb(doc.images or []),
                "videos": Jsonb(doc.videos or []),
                "extra": Jsonb(doc.extra or {}),
                "comment_count": len(doc.comments),
            },
        ).fetchone()
        document_id = row["id"]

        conn.execute(
            """
            INSERT INTO document_engagement_snapshots (document_id, comment_count)
            VALUES (%s, %s)
            """,
            (document_id, len(doc.comments)),
        )

        for i, comment in enumerate(doc.comments):
            conn.execute(
                """
                INSERT INTO document_comments (
                    document_id, external_comment_id, author, text, content_hash,
                    parent_comment_id, depth, match_key, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id, external_comment_id) DO UPDATE SET
                    text = EXCLUDED.text,
                    content_hash = EXCLUDED.content_hash,
                    is_edited = document_comments.content_hash <> EXCLUDED.content_hash
                """,
                (
                    document_id,
                    comment.external_comment_id,
                    comment.author,
                    comment.text,
                    _content_hash(comment.text),
                    comment.parent_comment_id,
                    comment.depth,
                    f"{comment.author or ''}|{comment.parent_comment_id or ''}|{i}",
                    comment.created_at,
                ),
            )
