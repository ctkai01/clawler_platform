"""Parse Facebook GraphQL / embedded JSON payloads found on a personal
profile timeline into fb_crawl.types.Post/Comment.

Ported from the reference project at
/home/ctkai/Documents/facebook_profile/fb_parser.py — that project sniffs
GraphQL responses + <script type="application/json"> payloads instead of
scraping the rendered DOM (unlike fb_crawl.parser, used for Group/Page),
because a personal profile's Timeline renders very differently from a
Page's feed and doesn't expose stable anchor-tag post links the same way.
Kept as raw-dict parsing (matching the reference project almost verbatim)
with a thin adapter (parsed_post_to_post/parsed_comment_to_comment) at the
bottom converting into this repo's dataclasses — safer than rewriting the
payload-walking logic to build dataclasses directly mid-walk.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from fb_crawl.types import Comment, Post, PostEngagement

REACTION_LABELS = {
    "LIKE": "like",
    "LOVE": "love",
    "HAHA": "haha",
    "WOW": "wow",
    "SAD": "sad",
    "ANGRY": "angry",
    "CARE": "care",
}

# Facebook không trả tên loại reaction trong top_reactions.edges[].node (chỉ có id),
# nên phải map theo id cố định của từng loại reaction.
REACTION_ID_LABELS = {
    "1635855486666999": "like",
    "1678524932434102": "love",
    "613557422527858": "haha",
    "115940658764963": "wow",
    "478547315650144": "sad",
    "908563459236466": "angry",
    "444813342392137": "care",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        if value.isdigit():
            return _parse_timestamp(int(value))
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_post_id(node: dict[str, Any]) -> str | None:
    for key in ("post_id", "legacy_post_id", "id", "feedback_id"):
        value = node.get(key)
        if isinstance(value, str) and value.isdigit():
            return value
    feedback = _as_dict(node.get("feedback"))
    for key in ("id", "legacy_api_post_id"):
        value = feedback.get(key)
        if isinstance(value, str) and value.isdigit():
            return value
    return None


def _extract_post_url(node: dict[str, Any], post_id: str | None) -> str | None:
    url = _first_str(node.get("url"), node.get("wwwURL"), node.get("permalink_url"))
    if url:
        return url
    if post_id:
        return f"https://www.facebook.com/{post_id}"
    return None


def _extract_content(node: dict[str, Any]) -> str:
    # node["message"]/["story_message"] là field TextWithEntities chính thức của
    # Facebook cho nội dung bài viết — LUÔN ưu tiên tuyệt đối, không quét thêm bất
    # cứ đâu khác. Quét sâu vào comet_sections (như trước đây) sẽ lẫn cả text của
    # các thành phần lân cận trong cùng cây UI (preview comment, thông báo "Commenting
    # has been turned off"...) vào nội dung bài viết dù chúng KHÔNG phải nội dung bài.
    for key in ("message", "story_message"):
        value = _as_dict(node.get(key))
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    # Fallback hiếm gặp: post không có message/story_message trực tiếp trên node —
    # quét comet_sections nhưng chỉ nhận đúng object TextWithEntities thật
    # ({"text": ..., "ranges": [...]}) để hạn chế rác tối đa.
    parts: list[str] = []

    def collect_message(obj: Any) -> None:
        if isinstance(obj, dict):
            if "tag" in obj and "children" in obj:
                return
            text = obj.get("text")
            if isinstance(text, str) and text.strip() and "ranges" in obj:
                parts.append(text.strip())
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    collect_message(value)
        elif isinstance(obj, list):
            for item in obj:
                collect_message(item)

    for key in ("comet_sections", "content"):
        if key in node:
            collect_message(node[key])

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part not in seen:
            seen.add(part)
            deduped.append(part)
    return "\n".join(deduped)


def _extract_images(node: dict[str, Any]) -> list[str]:
    images: list[str] = []
    seen_photo_ids: set[str] = set()

    def add_media(media: Any) -> None:
        media = _as_dict(media)
        if not media:
            return
        photo_id = media.get("id")
        if photo_id and photo_id in seen_photo_ids:
            return
        uri = _first_str(
            _as_dict(media.get("viewer_image")).get("uri"),
            _as_dict(media.get("image")).get("uri"),
        )
        if not uri:
            return
        if photo_id:
            seen_photo_ids.add(photo_id)
        images.append(uri)

    if "image" in node or "viewer_image" in node:
        add_media(node)

    for attachment in _as_list(node.get("attachments")):
        attachment = _as_dict(attachment)
        add_media(attachment.get("media"))
        styles_attachment = _as_dict(_as_dict(attachment.get("styles")).get("attachment"))
        sub_nodes = _as_dict(styles_attachment.get("all_subattachments")).get("nodes")
        for sub in _as_list(sub_nodes):
            add_media(_as_dict(sub).get("media"))

    return images


def _extract_reactions(node: dict[str, Any]) -> dict[str, int]:
    reactions: dict[str, int] = {"total": 0}
    feedback = _as_dict(node.get("feedback"))

    for source in (node, feedback):
        for key in ("reaction_count", "i18n_reaction_count", "total_count"):
            count = source.get(key)
            if isinstance(count, dict):
                total = count.get("count")
                if isinstance(total, int):
                    reactions["total"] = max(reactions["total"], total)
            elif isinstance(count, int):
                reactions["total"] = max(reactions["total"], count)

        for reactors_key in ("reactors", "unified_reactors"):
            reactors = _as_dict(source.get(reactors_key))
            total = reactors.get("count")
            if not isinstance(total, int):
                reduced = reactors.get("count_reduced")
                if isinstance(reduced, str) and reduced.isdigit():
                    total = int(reduced)
            if isinstance(total, int):
                reactions["total"] = max(reactions["total"], total)

        reaction_edges = _as_dict(source.get("top_reactions")).get("edges")
        if isinstance(reaction_edges, list):
            for edge in reaction_edges:
                edge = _as_dict(edge)
                reaction_node = _as_dict(edge.get("node"))
                reaction_type = _first_str(
                    reaction_node.get("localized_name"),
                    reaction_node.get("reaction_type"),
                ) or REACTION_ID_LABELS.get(reaction_node.get("id"))
                reaction_count = edge.get("reaction_count")
                if not isinstance(reaction_count, int):
                    reaction_count = reaction_node.get("reaction_count")
                if isinstance(reaction_count, int) and reaction_type:
                    label = REACTION_LABELS.get(reaction_type.upper(), reaction_type.lower())
                    reactions[label] = reaction_count

    if reactions["total"] == 0:
        reactions["total"] = sum(v for k, v in reactions.items() if k != "total")
    return reactions


def _extract_comment_count(node: dict[str, Any]) -> int:
    feedback = _as_dict(node.get("feedback"))
    for source in (node, feedback):
        for key in ("comment_count", "total_comment_count", "comments_count_summary"):
            value = source.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, dict):
                count = value.get("total_count") or value.get("count")
                if isinstance(count, int):
                    return count
    return 0


def _extract_privacy(node: dict[str, Any]) -> str | None:
    for key in ("privacy_scope", "privacy_label", "privacy_description"):
        value = node.get(key)
        if isinstance(value, str):
            return value.lower()
        if isinstance(value, dict):
            label = _first_str(value.get("label"), value.get("description"))
            if label:
                return label.lower()
    return None


def _has_video_attachment(node: dict[str, Any]) -> bool:
    """Phát hiện bài viết có gắn video, kể cả khi post_url là dạng /posts/pfbid...
    bình thường (không phải /reel/ hay /videos/) — Facebook cho phép đăng video
    trực tiếp trong 1 post thường, chỉ khác ở __typename của media đính kèm."""
    if str(node.get("__typename", "")) == "Video":
        return True

    def check_media(media: Any) -> bool:
        media = _as_dict(media)
        return str(media.get("__typename", "")) == "Video"

    video_style_markers = ("video", "reel", "shorts")

    for attachment in _as_list(node.get("attachments")):
        attachment = _as_dict(attachment)
        if check_media(attachment.get("media")):
            return True

        styles = _as_dict(attachment.get("styles"))
        styles_typename = str(styles.get("__typename", "")).lower()
        if any(marker in styles_typename for marker in video_style_markers):
            return True

        styles_attachment = _as_dict(styles.get("attachment"))
        if check_media(styles_attachment.get("media")):
            return True
        sub_nodes = _as_dict(styles_attachment.get("all_subattachments")).get("nodes")
        for sub in _as_list(sub_nodes):
            if check_media(_as_dict(sub).get("media")):
                return True

        # style_list thật nằm trong styles.attachment (không phải attachment gốc),
        # dạng ["fb_shorts", "fallback"] hoặc tương tự cho video/reel đính kèm.
        for candidate in (attachment.get("style_list"), styles_attachment.get("style_list")):
            if isinstance(candidate, list) and any(
                marker in str(s).lower() for s in candidate for marker in video_style_markers
            ):
                return True

        for info in _as_list(styles_attachment.get("style_infos")):
            info_typename = str(_as_dict(info).get("__typename", "")).lower()
            if any(marker in info_typename for marker in video_style_markers):
                return True
    return False


def _is_public_post(node: dict[str, Any]) -> bool:
    privacy = _extract_privacy(node) or ""
    if not privacy:
        return True
    public_markers = ("public", "công khai", "everyone", "mọi người")
    return any(marker in privacy for marker in public_markers)


def _looks_like_post_node(node: dict[str, Any]) -> bool:
    post_id = _extract_post_id(node)
    if not post_id:
        return False
    has_text = bool(_extract_content(node))
    has_images = bool(_extract_images(node))
    has_engagement = _extract_comment_count(node) > 0 or _extract_reactions(node)["total"] > 0
    has_real_url = bool(_first_str(node.get("url"), node.get("wwwURL"), node.get("permalink_url")))
    typename = str(node.get("__typename", ""))
    story_typenames = ("Story", "FeedUnit", "CometFeedStory", "TimelineAppCollection")
    if any(t in typename for t in story_typenames):
        # Đôi khi bắt được 1 Story "stub" chưa tải xong dữ liệu (không caption,
        # không ảnh, không tương tác, không cả url thật) trong lúc cuộn — không
        # phải bài đăng thật, bỏ qua để tránh entry rỗng toàn bộ.
        return has_text or has_images or has_engagement or has_real_url
    # Không phải node dạng Story: chỉ chấp nhận nếu có caption thật hoặc có tương
    # tác thật. Chỉ có ảnh không thôi (không caption/tương tác/typename Story) rất
    # hay là 1 ảnh lẻ trong album/lưới ảnh (photo grid, "photos of you"...) bị quét
    # nhầm thành bài đăng, không phải bài viết thật trên timeline.
    return has_text or has_engagement


def parse_post_node(node: dict[str, Any]) -> dict[str, Any] | None:
    if not _looks_like_post_node(node):
        return None

    post_id = _extract_post_id(node)
    if not post_id:
        return None

    published_at = None
    for key in ("creation_time", "created_time", "publish_time"):
        published_at = _parse_timestamp(node.get(key))
        if published_at:
            break
    if not published_at:
        for sub in _walk(node):
            for key in ("creation_time", "created_time", "publish_time"):
                published_at = _parse_timestamp(sub.get(key))
                if published_at:
                    break
            if published_at:
                break

    return {
        "post_id": post_id,
        "post_url": _extract_post_url(node, post_id),
        "content": _extract_content(node),
        "published_at": published_at.isoformat() if published_at else None,
        "images": _extract_images(node),
        "reactions": _extract_reactions(node),
        "comment_count": _extract_comment_count(node),
        "privacy": _extract_privacy(node),
        "is_public": _is_public_post(node),
        "is_video": _has_video_attachment(node),
    }


def merge_post_fields(current: dict[str, Any], new: dict[str, Any]) -> None:
    for key, value in new.items():
        if key == "images" and value:
            current["images"] = list(dict.fromkeys(current.get("images", []) + value))
        elif key == "reactions" and isinstance(value, dict):
            merged = current.setdefault("reactions", {"total": 0})
            merged["total"] = max(merged.get("total", 0), value.get("total", 0))
            for reaction_key, reaction_val in value.items():
                if reaction_key == "total":
                    continue
                merged[reaction_key] = max(merged.get(reaction_key, 0), reaction_val)
        elif key == "comment_count":
            current["comment_count"] = max(current.get("comment_count", 0), value or 0)
        elif value and not current.get(key):
            current[key] = value


def parse_posts_from_payload(payload: Any) -> list[dict[str, Any]]:
    posts: dict[str, dict[str, Any]] = {}
    # Cùng 1 post_id có thể khớp nhiều node trong payload (vd. node "Story" chính
    # không có field message/story_message trực tiếp nên content phải fallback
    # quét comet_sections, trong khi 1 node khác cùng post_id lại có message sạch).
    # Do thứ tự xử lý không đảm bảo node có message tới trước, nếu chỉ merge theo
    # kiểu "không ghi đè nếu đã có" thì content rác từ fallback có thể thắng trước
    # content sạch. Ghi nhận riêng content lấy trực tiếp từ message/story_message
    # để luôn ưu tiên áp dụng cuối cùng, bất kể thứ tự duyệt.
    authoritative_content: dict[str, str] = {}

    for node in _walk(payload):
        parsed = parse_post_node(node)
        if not parsed:
            continue
        post_id = parsed["post_id"]

        for key in ("message", "story_message"):
            msg = _as_dict(node.get(key))
            msg_text = msg.get("text")
            if isinstance(msg_text, str) and msg_text.strip():
                authoritative_content[post_id] = msg_text.strip()
                break

        if post_id not in posts:
            posts[post_id] = parsed
        else:
            merge_post_fields(posts[post_id], parsed)

    for post_id, text in authoritative_content.items():
        if post_id in posts:
            posts[post_id]["content"] = text

    return list(posts.values())


def parse_comment_node(node: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(node.get("body"), dict):
        return None
    text = _first_str(node["body"].get("text"))
    if not text:
        return None

    author = _as_dict(node.get("author"))
    author_name = _first_str(author.get("name"), author.get("short_name")) or "Unknown"
    author_id = _first_str(author.get("id"))

    reaction_count = 0
    feedback = _as_dict(node.get("feedback"))
    for source in (node, feedback):
        for key in ("reaction_count", "i18n_reaction_count"):
            value = source.get(key)
            if isinstance(value, int):
                reaction_count = max(reaction_count, value)
            elif isinstance(value, dict):
                count = value.get("count")
                if isinstance(count, int):
                    reaction_count = max(reaction_count, count)

    created_at = None
    for key in ("created_time", "creation_time"):
        created_at = _parse_timestamp(node.get(key))
        if created_at:
            break

    return {
        "comment_id": _first_str(node.get("id"), node.get("legacy_fbid")),
        "author": author_name,
        "author_id": author_id,
        "content": text,
        "reaction_count": reaction_count,
        "created_at": created_at.isoformat() if created_at else None,
    }


def parse_comments_from_payload(payload: Any) -> list[dict[str, Any]]:
    comments: dict[str, dict[str, Any]] = {}
    for node in _walk(payload):
        parsed = parse_comment_node(node)
        if parsed:
            key = parsed["comment_id"] or f"{parsed['author']}:{parsed['content'][:40]}"
            comments[key] = parsed
    return list(comments.values())


def top_comments(comments: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    ranked = sorted(
        comments,
        key=lambda item: (
            item.get("reaction_count", 0),
            len(item.get("content", "")),
        ),
        reverse=True,
    )
    return ranked[:limit]


_EMBEDDED_JSON_SCRIPT_RE = re.compile(
    r'<script type="application/json"[^>]*>(.*?)</script>', re.S
)


def extract_embedded_payloads(html: str) -> list[Any]:
    payloads: list[Any] = []
    for raw in _EMBEDDED_JSON_SCRIPT_RE.findall(html):
        try:
            payloads.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return payloads


def extract_graphql_payloads(text: str) -> list[Any]:
    payloads: list[Any] = []
    text = text.strip()
    if not text:
        return payloads

    if text.startswith("{"):
        try:
            payloads.append(json.loads(text))
            return payloads
        except json.JSONDecodeError:
            pass

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payloads.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return payloads


def post_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    for part in reversed(path_parts):
        if part.isdigit():
            return part
    query = parse_qs(parsed.query)
    for key in ("story_fbid", "fbid", "id"):
        values = query.get(key)
        if values and values[0].isdigit():
            return values[0]
    return None


def comment_story_id(comment_id: str | None) -> str | None:
    """Giải mã base64 của comment_id (dạng "comment:<story_id>_<suffix>") để lấy
    ra story_id mà comment đó thực sự thuộc về.

    Cần thiết vì: khi xem Reels, Facebook preload sẵn dữ liệu (bao gồm comment)
    của nhiều reel khác đang chờ ở hàng đợi tiếp theo trong CÙNG một response/
    payload — nếu không kiểm tra story_id, comment của các reel không liên quan
    sẽ bị gộp nhầm vào bài đang crawl."""
    if not comment_id:
        return None
    try:
        decoded = base64.b64decode(comment_id).decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return None
    if ":" not in decoded:
        return None
    payload = decoded.split(":", 1)[1]
    return payload.split("_")[0] if "_" in payload else payload


# -- Adapters: reference-project raw dict -> this repo's dataclasses --------


def parsed_post_to_post(raw: dict[str, Any], *, profile_id: str, author: str | None) -> Post:
    reactions = dict(raw.get("reactions") or {})
    total = int(reactions.pop("total", 0) or 0)
    reactions = {k: int(v) for k, v in reactions.items() if int(v or 0) > 0}
    published_at = _parse_timestamp(raw.get("published_at"))

    return Post(
        post_id=raw["post_id"],
        group_id=profile_id,
        page_id=profile_id,
        url=raw.get("post_url") or f"https://www.facebook.com/{raw['post_id']}",
        author=author or "",
        topic="",
        content=raw.get("content") or "",
        published_at=published_at,
        images=list(raw.get("images") or []),
        source_type="profile",
        engagement=PostEngagement(
            like_count=reactions.get("like", 0),
            comment_count=int(raw.get("comment_count") or 0),
            reaction_count=total or sum(reactions.values()),
            reactions=reactions,
        ),
    )


def parsed_comment_to_comment(raw: dict[str, Any]) -> Comment:
    created_at = _parse_timestamp(raw.get("created_at"))
    comment_id = raw.get("comment_id") or f"{raw.get('author')}:{(raw.get('content') or '')[:40]}"
    return Comment(
        comment_id=comment_id,
        author=raw.get("author") or "Unknown",
        text=raw.get("content") or "",
        created_at=created_at,
        author_id=raw.get("author_id"),
        engagement=PostEngagement(reaction_count=int(raw.get("reaction_count") or 0)),
    )
