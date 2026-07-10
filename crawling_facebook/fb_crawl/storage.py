from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from fb_crawl.parser import reactions_json, resolve_crawled_post_engagement
from fb_crawl.types import Comment, Post


def comment_match_key(comment: Comment) -> str:
    return f"{comment.author}|{comment.parent_comment_id or ''}|{comment.depth}"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    group_id TEXT PRIMARY KEY,
                    name TEXT,
                    url TEXT NOT NULL,
                    last_synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS pages (
                    page_id TEXT PRIMARY KEY,
                    name TEXT,
                    url TEXT NOT NULL,
                    last_synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS posts (
                    post_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    source_type TEXT DEFAULT 'group',
                    url TEXT NOT NULL,
                    author TEXT,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    published_at TEXT,
                    edited_at TEXT,
                    is_edited INTEGER DEFAULT 0,
                    images_json TEXT,
                    videos_json TEXT,
                    reaction_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    like_count INTEGER DEFAULT 0,
                    reactions_json TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS comments (
                    comment_id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    author TEXT,
                    author_id TEXT,
                    text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT,
                    first_seen_at TEXT NOT NULL,
                    match_key TEXT NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES posts(post_id)
                );

                CREATE INDEX IF NOT EXISTS idx_posts_group ON posts(group_id);
                CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source_type, group_id);
                CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
                """
            )
            self._ensure_column(conn, "groups", "name", "TEXT")
            self._ensure_column(conn, "posts", "source_type", "TEXT DEFAULT 'group'")
            self._ensure_column(conn, "posts", "videos_json", "TEXT")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        col_type: str,
    ) -> None:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def upsert_group(self, group_id: str, url: str, *, name: str | None = None) -> None:
        with self._conn() as conn:
            if name:
                conn.execute(
                    """
                    INSERT INTO groups (group_id, name, url) VALUES (?, ?, ?)
                    ON CONFLICT(group_id) DO UPDATE SET
                        url = excluded.url,
                        name = COALESCE(groups.name, excluded.name)
                    """,
                    (group_id, name, url),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO groups (group_id, url) VALUES (?, ?)
                    ON CONFLICT(group_id) DO UPDATE SET url = excluded.url
                    """,
                    (group_id, url),
                )

    def get_group(self, group_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM groups WHERE group_id = ?", (group_id,)).fetchone()
            return dict(row) if row else None

    def upsert_page(self, page_id: str, url: str, *, name: str | None = None) -> None:
        with self._conn() as conn:
            if name:
                conn.execute(
                    """
                    INSERT INTO pages (page_id, name, url) VALUES (?, ?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET
                        url = excluded.url,
                        name = COALESCE(pages.name, excluded.name)
                    """,
                    (page_id, name, url),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO pages (page_id, url) VALUES (?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET url = excluded.url
                    """,
                    (page_id, url),
                )

    def get_page(self, page_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM pages WHERE page_id = ?", (page_id,)).fetchone()
            return dict(row) if row else None

    def mark_page_synced(self, page_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE pages SET last_synced_at = ? WHERE page_id = ?",
                (_to_iso(_utcnow()), page_id),
            )

    def get_post(self, post_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()
            return dict(row) if row else None

    def save_post(self, post: Post) -> None:
        now = _to_iso(_utcnow())
        full_text = f"{post.topic or ''}\n{post.content}".strip()
        eng = resolve_crawled_post_engagement(
            post.engagement,
            parsed_comment_count=len(post.comments),
        )
        import json

        images_json = json.dumps(post.images, ensure_ascii=False)
        videos_json = json.dumps(post.videos, ensure_ascii=False)
        existing = self.get_post(post.post_id)
        owner_id = post.page_id if post.source_type == "page" else post.group_id
        source_type = post.source_type or "group"

        with self._conn() as conn:
            if not existing:
                conn.execute(
                    """
                    INSERT INTO posts (
                        post_id, group_id, source_type, url, author, content, content_hash,
                        published_at, edited_at, is_edited, images_json, videos_json,
                        reaction_count, comment_count, like_count, reactions_json,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post.post_id,
                        owner_id,
                        source_type,
                        post.url,
                        post.author,
                        full_text,
                        content_hash(full_text),
                        _to_iso(post.published_at),
                        _to_iso(post.edited_at),
                        int(post.is_edited),
                        images_json,
                        videos_json,
                        eng.reaction_count,
                        eng.comment_count,
                        eng.like_count,
                        reactions_json(eng),
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE posts SET
                        url = ?, author = ?, content = ?, content_hash = ?,
                        published_at = COALESCE(?, published_at),
                        edited_at = COALESCE(?, edited_at),
                        is_edited = ?,
                        images_json = ?,
                        videos_json = ?,
                        reaction_count = ?, comment_count = ?, like_count = ?,
                        reactions_json = ?, last_seen_at = ?
                    WHERE post_id = ?
                    """,
                    (
                        post.url,
                        post.author,
                        full_text,
                        content_hash(full_text),
                        _to_iso(post.published_at),
                        _to_iso(post.edited_at),
                        int(post.is_edited or bool(existing["is_edited"])),
                        images_json,
                        videos_json,
                        eng.reaction_count,
                        eng.comment_count,
                        eng.like_count,
                        reactions_json(eng),
                        now,
                        post.post_id,
                    ),
                )

    def upsert_comments(self, post_id: str, comments: list[Comment]) -> list[Comment]:
        now = _to_iso(_utcnow())
        new_comments: list[Comment] = []

        with self._conn() as conn:
            existing_rows = conn.execute(
                "SELECT comment_id, match_key, content_hash FROM comments WHERE post_id = ?",
                (post_id,),
            ).fetchall()
            by_match = {r["match_key"]: dict(r) for r in existing_rows}
            seen_ids = {r["comment_id"] for r in existing_rows}

            for comment in comments:
                key = comment_match_key(comment)
                row = by_match.get(key)
                if row:
                    if row["content_hash"] != content_hash(comment.text):
                        conn.execute(
                            """
                            UPDATE comments SET text = ?, content_hash = ?, created_at = COALESCE(?, created_at)
                            WHERE comment_id = ?
                            """,
                            (
                                comment.text,
                                content_hash(comment.text),
                                _to_iso(comment.created_at),
                                row["comment_id"],
                            ),
                        )
                    continue

                comment_id = comment.comment_id
                if comment_id in seen_ids:
                    continue

                try:
                    conn.execute(
                        """
                        INSERT INTO comments (
                            comment_id, post_id, author, author_id, text,
                            content_hash, created_at, first_seen_at, match_key
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            comment_id,
                            post_id,
                            comment.author,
                            comment.author_id,
                            comment.text,
                            content_hash(comment.text),
                            _to_iso(comment.created_at),
                            now,
                            key,
                        ),
                    )
                    seen_ids.add(comment_id)
                    by_match[key] = {"comment_id": comment_id, "match_key": key, "content_hash": content_hash(comment.text)}
                    new_comments.append(comment)
                except sqlite3.IntegrityError:
                    continue

        return new_comments

    def list_posts_to_recheck(
        self,
        owner_id: str,
        *,
        since_hours: float = 48,
        source_type: str = "group",
    ) -> list[dict]:
        since = _utcnow() - timedelta(hours=since_hours)
        iso = _to_iso(since)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM posts WHERE group_id = ? AND source_type = ?
                AND comment_count > 0
                AND (
                    published_at >= ?
                    OR (published_at IS NULL AND first_seen_at >= ?)
                )
                ORDER BY last_seen_at DESC
                LIMIT 25
                """,
                (owner_id, source_type, iso, iso),
            ).fetchall()
            return [dict(r) for r in rows]

    def known_post_ids(self, owner_id: str, *, source_type: str = "group") -> set[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT post_id FROM posts WHERE group_id = ? AND source_type = ?",
                (owner_id, source_type),
            ).fetchall()
        return {r["post_id"] for r in rows}

    def mark_group_synced(self, group_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE groups SET last_synced_at = ? WHERE group_id = ?",
                (_to_iso(_utcnow()), group_id),
            )

    def known_comment_ids(self, post_id: str) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT comment_id FROM comments WHERE post_id = ?",
                (post_id,),
            ).fetchall()
            return {r["comment_id"] for r in rows}
