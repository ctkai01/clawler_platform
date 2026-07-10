from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NotGroupMemberError(RuntimeError):
    """The crawling account can see the group's public shell (name, member
    count) but not its feed — Facebook gates post content behind group
    membership even for "Public" groups. Distinct from a dead/expired
    session: re-logging in won't fix this, joining the group will."""


class PostChangeType(str, Enum):
    NEW = "new"
    CONTENT_EDITED = "content_edited"
    NEW_COMMENTS = "new_comments"
    COMMENT_EDITED = "comment_edited"
    ENGAGEMENT_CHANGED = "engagement_changed"
    REACTIONS_CHANGED = "engagement_changed"  # alias


@dataclass
class PostEngagement:
    like_count: int = 0
    share_count: int = 0
    comment_count: int = 0
    reaction_count: int = 0
    reactions: dict[str, int] = field(default_factory=dict)


@dataclass
class Comment:
    comment_id: str
    author: str
    text: str
    created_at: datetime | None = None
    parent_comment_id: str | None = None
    depth: int = 0
    is_edited: bool = False
    previous_text: str | None = None
    author_id: str | None = None
    engagement: PostEngagement = field(default_factory=PostEngagement)


@dataclass
class Post:
    post_id: str
    group_id: str
    url: str
    author: str
    topic: str
    content: str
    published_at: datetime | None = None
    edited_at: datetime | None = None
    author_id: str | None = None
    engagement: PostEngagement = field(default_factory=PostEngagement)
    is_edited: bool = False
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    source_type: str = "group"
    page_id: str | None = None
    comments: list[Comment] = field(default_factory=list)

    @property
    def reaction_count(self) -> int:
        return self.engagement.reaction_count

    @reaction_count.setter
    def reaction_count(self, value: int) -> None:
        self.engagement.reaction_count = value

    @property
    def comment_count(self) -> int:
        return self.engagement.comment_count

    @comment_count.setter
    def comment_count(self, value: int) -> None:
        self.engagement.comment_count = value

    @property
    def like_count(self) -> int:
        return self.engagement.like_count

    @property
    def share_count(self) -> int:
        return self.engagement.share_count


@dataclass
class CommentChange:
    comment: Comment
    change_type: str  # new | edited
    previous_text: str | None = None


@dataclass
class PostChange:
    post_id: str
    change_type: PostChangeType
    post: Post
    previous_content: str | None = None
    new_comments: list[Comment] = field(default_factory=list)
    edited_comments: list[Comment] = field(default_factory=list)
    engagement_delta: dict[str, int] = field(default_factory=dict)


@dataclass
class PostCycleDetail:
    post_id: str
    url: str
    author: str
    topic: str
    is_new: bool = False
    content_edited: bool = False
    comment_count: int = 0
    like_count: int = 0
    love_count: int = 0
    angry_count: int = 0
    sad_count: int = 0
    reaction_count: int = 0
    comments_new: int = 0
    comments_edited: int = 0
    comment_delta: int = 0
    like_delta: int = 0
    love_delta: int = 0
    angry_delta: int = 0
    sad_delta: int = 0
    reaction_delta: int = 0
    reactions_extra_delta: dict[str, int] = field(default_factory=dict)

    def has_engagement_change(self) -> bool:
        if any(
            (
                self.like_delta,
                self.love_delta,
                self.angry_delta,
                self.sad_delta,
                self.reaction_delta,
            )
        ):
            return True
        return any(self.reactions_extra_delta.values())
