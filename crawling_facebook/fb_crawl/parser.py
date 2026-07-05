from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fb_crawl.types import Comment, Post, PostEngagement

_FB_POST_ID_RE = re.compile(
    r"(?:/groups/\d+/posts/(\d+)|/permalink/(\d+)|story_fbid=(\d+)|/posts/([^/?#]+)|/share/p/([^/?]+)|/videos/(\d+)|[?&]v=(\d+)|[?&]fbid=(\d+))"
)
_PAGE_RESERVED = frozenset({
    "groups", "watch", "photo", "permalink.php", "story.php", "share",
    "login", "recover", "help", "policies", "privacy", "marketplace",
    "gaming", "reel", "reels", "events", "friends", "notifications",
    "messages", "settings", "pages", "profile.php", "people",
})
_EDITED_RE = re.compile(r"(đã chỉnh sửa|edited)", re.I)
_SKIP_LINES = {
    "thích", "bình luận", "chia sẻ", "like", "comment", "share",
    "trả lời", "reply", "phản hồi",
}
_TIME_PATTERNS = [
    (re.compile(r"(\d+)\s*phút", re.I), "minutes"),
    (re.compile(r"(\d+)\s*giờ", re.I), "hours"),
    (re.compile(r"(\d+)\s*giây", re.I), "seconds"),
    (re.compile(r"(\d+)\s*ngày(?:\s+trước)?", re.I), "days"),
    (re.compile(r"(\d+)\s*tuần(?:\s+trước)?", re.I), "weeks"),
    (re.compile(r"(\d+)\s*tháng\s+trước", re.I), "months"),
    (re.compile(r"(\d+)\s*năm\s+trước", re.I), "years"),
    (re.compile(r"(\d+)\s*min", re.I), "minutes"),
    (re.compile(r"(\d+)\s*hr", re.I), "hours"),
    (re.compile(r"(\d+)\s*h\b", re.I), "hours"),
    (re.compile(r"(\d+)\s*m\b", re.I), "minutes"),
    (re.compile(r"(\d+)\s*d\b", re.I), "days"),
    (re.compile(r"(\d+)\s*days?\s+ago", re.I), "days"),
    (re.compile(r"(\d+)\s*day", re.I), "days"),
    (re.compile(r"(\d+)\s*w\b", re.I), "weeks"),
    (re.compile(r"(\d+)\s*weeks?\s+ago", re.I), "weeks"),
    (re.compile(r"(\d+)\s*months?\s+ago", re.I), "months"),
    (re.compile(r"(\d+)\s*years?\s+ago", re.I), "years"),
]
_MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_CLOCK_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s*(am|pm)?",
    re.I,
)
_ABSOLUTE_DATE_RE = re.compile(
    r"(?:(\d{1,2})\s*(?:tháng|thg)\s*(\d{1,2})"
    r"|(?:tháng|thg)\s*(\d{1,2})\s*(?:ngày)?\s*(\d{1,2})"
    r"|([a-z]+)\s+(\d{1,2})"
    r"|(\d{1,2})\s+([a-z]+))"
    r"(?:\s*(?:lúc|at|,)\s*(\d{1,2}):(\d{2})\s*(am|pm)?)?",
    re.I,
)


def _to_24h(hour: int, minute: int, ampm: str | None) -> tuple[int, int]:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    return hour, minute


def _dt_from_date_time(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _parse_absolute_date(text: str, now: datetime) -> datetime | None:
    m = _ABSOLUTE_DATE_RE.search(text)
    if not m:
        return None

    hour, minute = 12, 0
    if m.group(9):
        hour, minute = _to_24h(int(m.group(9)), int(m.group(10)), m.group(11))

    if m.group(1) and m.group(2):
        day, month = int(m.group(1)), int(m.group(2))
    elif m.group(3) and m.group(4):
        month, day = int(m.group(3)), int(m.group(4))
    elif m.group(5) and m.group(6):
        month = _MONTH_NAMES.get(m.group(5).lower())
        if not month:
            return None
        day = int(m.group(6))
    elif m.group(7) and m.group(8):
        day = int(m.group(7))
        month = _MONTH_NAMES.get(m.group(8).lower())
        if not month:
            return None
    else:
        return None

    year = now.year
    try:
        candidate = _dt_from_date_time(year, month, day, hour, minute)
    except ValueError:
        return None
    if candidate > now + timedelta(hours=2):
        try:
            candidate = _dt_from_date_time(year - 1, month, day, hour, minute)
        except ValueError:
            return None
    return candidate


def _parse_day_with_clock(text: str, now: datetime, *, day_offset: int) -> datetime | None:
    m = _CLOCK_RE.search(text)
    if not m:
        return now + timedelta(days=day_offset)
    hour, minute = _to_24h(int(m.group(1)), int(m.group(2)), m.group(3))
    base = (now + timedelta(days=day_offset)).date()
    return _dt_from_date_time(base.year, base.month, base.day, hour, minute)
_REACTION_LABELS: list[tuple[str, list[str]]] = [
    ("love", ["yêu thích", "love"]),
    ("care", ["thương thương", "care"]),
    ("angry", ["phẫn nộ", "angry"]),
    ("sad", ["buồn", "sad"]),
    ("haha", ["haha", "ha ha"]),
    ("wow", ["wow", "ngạc nhiên"]),
    ("like", ["thích", "like"]),
]


def extract_post_id(url: str) -> str | None:
    for match in _FB_POST_ID_RE.finditer(url):
        for group in match.groups():
            if group and group.isdigit():
                return group
            if group and not group.isdigit():
                return group  # share/p/ slug — resolved after redirect
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ("story_fbid", "fbid"):
        if key in qs and qs[key]:
            return qs[key][0]
    return None


def extract_group_id(url: str) -> str | None:
    # Facebook chấp nhận cả group_id dạng số lẫn slug chữ (vanity URL) như nhau.
    match = re.search(r"/groups/([^/?#]+)", url)
    return match.group(1) if match else None


def extract_page_id(url: str) -> str | None:
    """Lấy slug hoặc numeric ID của Facebook Page từ URL."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host and "facebook.com" not in host:
        return None

    qs = parse_qs(parsed.query)
    for key in ("id", "page_id"):
        if key in qs and qs[key]:
            val = qs[key][0].strip()
            if val.isdigit():
                return val

    path = parsed.path.strip("/")
    if not path:
        return None
    if path.startswith("groups/"):
        return None

    parts = [p for p in path.split("/") if p]
    if not parts:
        return None

    first = parts[0].lower()
    if first in _PAGE_RESERVED:
        return None

    if first == "profile.php":
        pid = qs.get("id", [None])[0]
        return pid.strip() if pid else None

    if len(parts) >= 2 and parts[1] in ("posts", "videos", "photos", "reels", "reel"):
        slug = parts[0]
        if slug.lower() not in _PAGE_RESERVED:
            return slug

    if first not in _PAGE_RESERVED:
        return parts[0]
    return None


def normalize_page_url(url: str) -> str:
    page_id = extract_page_id(url)
    if not page_id:
        return url.split("?")[0].rstrip("/")
    return f"https://www.facebook.com/{page_id}"


def normalize_page_post_url(url: str, page_id: str | None = None) -> str | None:
    pid = extract_page_id(url) or page_id
    post_id = extract_post_id(url)
    if not pid or not post_id:
        return None
    if post_id.isdigit():
        return f"https://www.facebook.com/{pid}/posts/{post_id}"
    return f"https://www.facebook.com/{pid}/posts/{post_id}"


def dedupe_page_post_urls(urls: list[str], page_id: str | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in urls:
        normalized = normalize_page_post_url(raw, page_id) or raw.split("?")[0].rstrip("/")
        pid = extract_post_id(normalized) or normalized
        if pid in seen:
            continue
        seen.add(pid)
        canonical = normalize_page_post_url(normalized, page_id)
        result.append(canonical or normalized)
    return result


def page_url_matches(page_id: str, href: str) -> bool:
    if not page_id:
        return True
    key = page_id.lower()
    href_l = href.lower()
    if f"/{key}/" in href_l or href_l.endswith(f"/{key}"):
        return True
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    for qkey in ("id", "page_id"):
        if qkey in qs and qs[qkey][0].lower() == key:
            return True
    return False


def extract_user_id(url: str) -> str | None:
    """Lấy Facebook user ID từ URL profile."""
    if not url:
        return None
    patterns = [
        re.compile(r"/user/(\d+)", re.I),
        re.compile(r"/groups/\d+/user/(\d+)", re.I),
        re.compile(r"/people/[^/?#]+/(\d+)", re.I),
        re.compile(r"[?&]id=(\d+)", re.I),
    ]
    for pattern in patterns:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def is_anonymous_author(name: str | None) -> bool:
    if not name or not name.strip():
        return True
    return bool(re.match(r"^(ẩn danh|anonymous|unknown)$", name.strip(), re.I))


def normalize_group_post_url(url: str, group_id: str | None = None) -> str | None:
    """Chuẩn hoá URL bài viết nhóm → permalink (giống paste link bài)."""
    gid = extract_group_id(url) or group_id
    pid = extract_post_id(url)
    if gid and pid and pid.isdigit():
        return f"https://www.facebook.com/groups/{gid}/permalink/{pid}/"
    return None


def dedupe_post_urls(urls: list[str], group_id: str | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in urls:
        normalized = normalize_group_post_url(raw, group_id) or raw.split("?")[0].rstrip("/")
        pid = extract_post_id(normalized)
        key = pid or normalized
        if key in seen:
            continue
        seen.add(key)
        if normalize_group_post_url(normalized, group_id):
            result.append(normalize_group_post_url(normalized, group_id) or normalized)
        elif pid and group_id:
            result.append(f"https://www.facebook.com/groups/{group_id}/permalink/{pid}/")
        else:
            result.append(normalized)
    return result


_TOOLTIP_DATETIME_RE = re.compile(
    r"(\d{1,2})\s*(?:tháng|thg)\s*(\d{1,2}),?\s*(\d{4})\s*(?:lúc|at)\s*(\d{1,2}):(\d{2})",
    re.I,
)


def parse_fb_tooltip_datetime(text: str) -> datetime | None:
    """Parse Facebook's precise hover-tooltip timestamp, e.g.
    'Chủ Nhật, 24 Tháng 5, 2026 lúc 14:32' (day-month-year explicit, unlike
    the relative "N tuần trước" labels FB shows by default). The browser
    context has no timezone configured so this renders in UTC — stored as
    UTC-aware to match the rest of the pipeline."""
    m = _TOOLTIP_DATETIME_RE.search(text)
    if not m:
        return None
    day, month, year, hour, minute = (int(g) for g in m.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_relative_time(text: str, now: datetime | None = None) -> datetime | None:
    """Chuyển chuỗi thời gian Facebook → datetime UTC (now = thời điểm crawl)."""
    now = now or datetime.now(timezone.utc)
    text = text.strip()
    if not text:
        return None
    lower = text.lower()

    tooltip = parse_fb_tooltip_datetime(text)
    if tooltip:
        return tooltip

    if "vừa xong" in lower or "just now" in lower:
        return now

    if re.search(r"\b(?:yesterday|hôm qua)\b", lower):
        return _parse_day_with_clock(text, now, day_offset=-1)

    if re.search(r"\b(?:today|hôm nay)\b", lower):
        return _parse_day_with_clock(text, now, day_offset=0)

    absolute = _parse_absolute_date(text, now)
    if absolute:
        return absolute

    for pattern, unit in _TIME_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        value = int(m.group(1))
        try:
            if unit == "minutes":
                return now - timedelta(minutes=value)
            if unit == "hours":
                return now - timedelta(hours=value)
            if unit == "seconds":
                return now - timedelta(seconds=value)
            if unit == "days":
                return now - timedelta(days=value)
            if unit == "weeks":
                return now - timedelta(weeks=value)
            if unit == "months":
                return now - timedelta(days=value * 30)
            if unit == "years":
                return now - timedelta(days=value * 365)
        except (ValueError, OverflowError):
            return None
    return None


def _stable_id(*parts: str) -> str:
    raw = "|".join(p.strip() for p in parts if p)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _parse_count(text: str, keywords: list[str]) -> int:
    for kw in keywords:
        pattern = re.compile(rf"(\d[\d.,]*)\s*{re.escape(kw)}", re.I)
        m = pattern.search(text)
        if m:
            return int(m.group(1).replace(".", "").replace(",", ""))
    return 0


def reaction_breakdown_sum(eng: PostEngagement) -> int:
    reactions = eng.reactions or {}
    like_count = resolved_like_count(
        like_count=eng.like_count,
        reactions=reactions,
        reaction_count=eng.reaction_count,
    )
    return like_count + sum(
        int(v or 0) for k, v in reactions.items() if k != "like"
    )


def normalize_post_engagement(eng: PostEngagement) -> PostEngagement:
    """Chuẩn hóa: Thích/love/angry/sad + loại khác = Tổng cảm xúc."""
    reactions = {
        str(k): int(v)
        for k, v in (eng.reactions or {}).items()
        if int(v or 0) > 0
    }
    reactions.pop("like", None)
    reactions.pop("other", None)

    like_count = resolved_like_count(
        like_count=eng.like_count,
        reactions=reactions,
        reaction_count=eng.reaction_count,
    )
    breakdown = like_count + sum(reactions.values())
    reaction_count = int(eng.reaction_count or 0)

    if reaction_count == 0:
        reaction_count = breakdown
    elif breakdown > reaction_count:
        reaction_count = breakdown
    elif reaction_count > breakdown:
        reactions["other"] = reactions.get("other", 0) + (reaction_count - breakdown)

    return PostEngagement(
        like_count=like_count,
        share_count=int(eng.share_count or 0),
        comment_count=int(eng.comment_count or 0),
        reaction_count=reaction_count,
        reactions=reactions,
    )


def engagement_to_api_dict(eng: PostEngagement) -> dict:
    eng = normalize_post_engagement(eng)
    reactions = eng.reactions or {}
    return {
        "like_count": eng.like_count,
        "love_count": reactions.get("love", 0) or 0,
        "angry_count": reactions.get("angry", 0) or 0,
        "sad_count": reactions.get("sad", 0) or 0,
        "other_count": reactions.get("other", 0) or 0,
        "share_count": eng.share_count,
        "comment_count": eng.comment_count,
        "reaction_count": eng.reaction_count,
        "reactions": reactions,
        "breakdown_sum": reaction_breakdown_sum(eng),
    }


def resolved_like_count(
    *,
    like_count: int = 0,
    reactions: dict[str, int] | None = None,
    reaction_count: int = 0,
) -> int:
    """Chỉ trả về số Thích — không dùng tổng cảm xúc (reaction_count)."""
    reactions = reactions or {}
    like = int(like_count or 0) or int(reactions.get("like", 0) or 0)
    other = sum(
        int(v or 0) for k, v in reactions.items() if k != "like"
    )
    total = int(reaction_count or 0)
    if like and total and like == total and other > 0:
        return int(reactions.get("like", 0) or 0)
    return like


def engagement_metrics(eng: PostEngagement, *, comment_fallback: int = 0) -> dict[str, int]:
    eng = normalize_post_engagement(eng)
    reactions = eng.reactions or {}
    comment_count = eng.comment_count or comment_fallback or 0
    return {
        "comment_count": comment_count,
        "like_count": eng.like_count,
        "love_count": reactions.get("love", 0) or 0,
        "angry_count": reactions.get("angry", 0) or 0,
        "sad_count": reactions.get("sad", 0) or 0,
        "other_count": reactions.get("other", 0) or 0,
        "reaction_count": eng.reaction_count or 0,
    }


_EXTRA_REACTION_KEYS = frozenset({"like", "love", "angry", "sad"})


def extra_reaction_counts(reactions: dict[str, int] | None) -> dict[str, int]:
    reactions = reactions or {}
    return {
        str(k): int(v)
        for k, v in reactions.items()
        if k not in _EXTRA_REACTION_KEYS and int(v or 0) > 0
    }


def compute_engagement_delta(
    existing: dict | None,
    eng: PostEngagement,
    *,
    comment_fallback: int = 0,
) -> dict[str, int]:
    """So sánh cảm xúc chu kỳ trước (DB) với giá trị crawl hiện tại."""
    prev = metrics_from_post_row(existing)
    prev_reactions = (
        parse_reactions_json(existing.get("reactions_json")) if existing else {}
    )
    curr = engagement_metrics(eng, comment_fallback=comment_fallback)
    curr_reactions = eng.reactions or {}

    delta: dict[str, int] = {}
    for key in (
        "comment_count",
        "like_count",
        "love_count",
        "angry_count",
        "sad_count",
        "reaction_count",
    ):
        diff = curr[key] - prev.get(key, 0)
        if diff != 0:
            delta[key] = diff

    share_diff = (eng.share_count or 0) - ((existing or {}).get("share_count") or 0)
    if share_diff != 0:
        delta["share_count"] = share_diff

    for key in set(extra_reaction_counts(prev_reactions)) | set(
        extra_reaction_counts(curr_reactions)
    ):
        diff = extra_reaction_counts(curr_reactions).get(key, 0) - extra_reaction_counts(
            prev_reactions
        ).get(key, 0)
        if diff != 0:
            delta[f"reactions.{key}"] = diff

    return delta


def metrics_from_post_row(row: dict | None) -> dict[str, int]:
    if not row:
        return {
            "comment_count": 0,
            "like_count": 0,
            "love_count": 0,
            "angry_count": 0,
            "sad_count": 0,
            "reaction_count": 0,
        }
    reactions = parse_reactions_json(row.get("reactions_json"))
    return {
        "comment_count": row.get("comment_count") or 0,
        "like_count": resolved_like_count(
            like_count=row.get("like_count") or 0,
            reactions=reactions,
            reaction_count=row.get("reaction_count") or 0,
        ),
        "love_count": reactions.get("love", 0) or 0,
        "angry_count": reactions.get("angry", 0) or 0,
        "sad_count": reactions.get("sad", 0) or 0,
        "reaction_count": row.get("reaction_count") or 0,
    }


def engagement_has_data(eng: PostEngagement) -> bool:
    if eng.like_count or eng.reaction_count or eng.comment_count or eng.share_count:
        return True
    return any(int(v or 0) > 0 for v in (eng.reactions or {}).values())


def resolve_crawled_post_engagement(
    eng: PostEngagement,
    *,
    parsed_comment_count: int = 0,
) -> PostEngagement:
    """Chuẩn hóa engagement từ lần crawl hiện tại (không gộp với DB)."""
    eng = normalize_post_engagement(eng)
    return PostEngagement(
        like_count=int(eng.like_count or 0),
        share_count=int(eng.share_count or 0),
        comment_count=max(int(eng.comment_count or 0), int(parsed_comment_count or 0)),
        reaction_count=int(eng.reaction_count or 0),
        reactions={
            str(k): int(v)
            for k, v in (eng.reactions or {}).items()
            if int(v or 0) > 0
        },
    )


def crawled_engagement_usable(
    eng: PostEngagement,
    *,
    parsed_comment_count: int = 0,
) -> bool:
    """Crawl có đủ tín hiệu để ghi đè engagement đã lưu."""
    if parsed_comment_count > 0:
        return True
    eng = normalize_post_engagement(eng)
    if (
        eng.comment_count
        or eng.share_count
        or eng.like_count
        or eng.reaction_count
    ):
        return True
    return any(int(v or 0) > 0 for v in (eng.reactions or {}).values())


def engagement_from_dict(data: dict | None) -> PostEngagement:
    if not data:
        return PostEngagement()
    reactions: dict[str, int] = {}
    for key, val in (data.get("reactions") or {}).items():
        try:
            n = int(val)
            if n > 0:
                reactions[str(key)] = n
        except (TypeError, ValueError):
            continue
    return normalize_post_engagement(
        PostEngagement(
            like_count=int(data.get("like_count") or 0),
            share_count=int(data.get("share_count") or 0),
            comment_count=int(data.get("comment_count") or 0),
            reaction_count=int(data.get("reaction_count") or 0),
            reactions=reactions,
        )
    )


def parse_engagement(text: str) -> PostEngagement:
    reactions: dict[str, int] = {}
    for key, labels in _REACTION_LABELS:
        count = _parse_count(text, labels)
        if count:
            reactions[key] = count

    like_count = reactions.get("like") or _parse_count(text, ["thích", "like", "lượt thích"])
    share_count = _parse_count(text, ["chia sẻ", "share", "lượt chia sẻ"])
    comment_count = _parse_count(text, ["bình luận", "comment", "lượt bình luận"])
    reaction_count = sum(reactions.values()) if reactions else like_count

    # Removed: a "<số> người" fallback used to backfill reaction_count when no
    # reaction breakdown was found. Real bug found in production — "người"
    # ("people") also appears in unrelated numbers scraped alongside a post
    # (observed: a Facebook group's own member count, e.g. "406.085 người"),
    # which got misread as that post's reaction count. Confirmed by real
    # data: ~24% of crawled posts had like/reaction counts in the hundreds of
    # thousands, clustered by source group rather than by post. Leaving
    # reaction_count at like_count (set above) when no breakdown is found is
    # the safe fallback — it may undercount but never fabricates a number.

    return normalize_post_engagement(
        PostEngagement(
            like_count=like_count,
            share_count=share_count,
            comment_count=comment_count,
            reaction_count=reaction_count or like_count,
            reactions=reactions,
        )
    )


def split_topic_and_body(lines: list[str]) -> tuple[str, str]:
    if not lines:
        return "", ""
    if len(lines) == 1:
        return lines[0], ""
    first, second = lines[0], lines[1]
    if len(first) <= 150 and len(second) > len(first):
        return first, "\n".join(lines[1:])
    return first, "\n".join(lines[1:]) if len(lines) > 1 else ""


def parse_post_from_element(
    element_html: str,
    element_text: str,
    *,
    group_id: str,
    post_url: str | None = None,
) -> Post | None:
    post_id = extract_post_id(post_url or element_html) or _stable_id(group_id, element_text[:200])
    if not post_id:
        return None

    lines = [ln.strip() for ln in element_text.splitlines() if ln.strip()]
    author = lines[0] if lines else ""
    body_lines: list[str] = []
    is_edited = bool(_EDITED_RE.search(element_text))
    published_at: datetime | None = None

    for line in lines[1:]:
        if _EDITED_RE.search(line) and len(line) < 30:
            is_edited = True
            continue
        maybe_time = parse_relative_time(line)
        if maybe_time and len(line) < 25:
            published_at = maybe_time
            continue
        if line.lower() in _SKIP_LINES:
            continue
        if re.match(r"^\d[\d.,]*\s*(thích|like|bình luận|comment|chia sẻ|share)", line, re.I):
            continue
        body_lines.append(line)

    topic, content = split_topic_and_body(body_lines)
    if not topic and body_lines:
        topic = body_lines[0]
        content = "\n".join(body_lines[1:])

    engagement = parse_engagement(element_text)
    url = post_url or f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"

    return Post(
        post_id=post_id,
        group_id=group_id,
        url=url,
        author=author,
        topic=topic,
        content=content,
        published_at=published_at,
        engagement=engagement,
        is_edited=is_edited,
    )


def parse_comment_line_block(
    block: str,
    *,
    depth: int = 0,
    parent_comment_id: str | None = None,
    time_text: str | None = None,
    now: datetime | None = None,
    engagement_data: dict | None = None,
    author_id: str | None = None,
) -> Comment | None:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    author = lines[0]
    body_parts: list[str] = []
    created_at: datetime | None = None
    crawl_time = now or datetime.now(timezone.utc)
    for line in lines[1:]:
        t = parse_relative_time(line, now=crawl_time)
        if t and len(line) < 40:
            created_at = t
            continue
        if line.lower() in _SKIP_LINES:
            continue
        body_parts.append(line)
    text = "\n".join(body_parts).strip()
    if not text:
        return None
    if not created_at and time_text:
        created_at = parse_relative_time(time_text, now=crawl_time)
    # Deliberately excludes `index` (position in the crawled list): that
    # position shifts across crawls whenever a new comment appears earlier
    # in the thread, which silently changed a real comment's id from one
    # crawl to the next and caused it to be re-inserted as a "new" row
    # instead of recognized as already-known. Content (author+text+depth+
    # parent) is what actually identifies a comment.
    comment_id = _stable_id(author, text, str(depth), str(parent_comment_id or ""))
    return Comment(
        comment_id=comment_id,
        author=author,
        text=text,
        created_at=created_at,
        parent_comment_id=parent_comment_id,
        depth=depth,
        author_id=author_id or None,
        engagement=engagement_from_dict(engagement_data),
    )


def parse_comments_structured(
    items: list[dict],
    *,
    now: datetime | None = None,
) -> list[Comment]:
    crawl_time = now or datetime.now(timezone.utc)
    comments: list[Comment] = []
    last_at_depth: dict[int, str] = {}

    for item in items:
        depth = int(item.get("depth", 0))
        parent_id = last_at_depth.get(depth - 1) if depth > 0 else None
        block = item.get("text") or item.get("block") or ""
        if not block and item.get("author") and item.get("body"):
            block = f"{item['author']}\n{item['body']}"
        time_text = (item.get("time") or "").strip() or None
        raw_author_id = item.get("author_id") or item.get("authorId")
        author_id = str(raw_author_id).strip() if raw_author_id else None

        comment = parse_comment_line_block(
            block,
            depth=depth,
            parent_comment_id=parent_id,
            time_text=time_text,
            now=crawl_time,
            engagement_data=item.get("engagement"),
            author_id=author_id,
        )
        if not comment:
            continue
        comments.append(comment)
        last_at_depth[depth] = comment.comment_id
        for k in list(last_at_depth):
            if k > depth:
                del last_at_depth[k]

    return comments


def parse_comments_from_page(text_blocks: list[str], *, now: datetime | None = None) -> list[Comment]:
    items = [{"text": block, "depth": 0} for block in text_blocks]
    return parse_comments_structured(items, now=now)


def build_comment_tree(comments: list[dict]) -> list[dict]:
    nodes: dict[str, dict] = {}
    for row in comments:
        nodes[row["comment_id"]] = {
            **row,
            "replies": [],
        }
    roots: list[dict] = []
    for row in comments:
        node = nodes[row["comment_id"]]
        parent_id = row.get("parent_comment_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["replies"].append(node)
        else:
            roots.append(node)
    return roots


def engagement_to_dict(engagement: PostEngagement) -> dict:
    return {
        "like_count": engagement.like_count,
        "share_count": engagement.share_count,
        "comment_count": engagement.comment_count,
        "reaction_count": engagement.reaction_count,
        "reactions": engagement.reactions,
    }


def reactions_json(engagement: PostEngagement) -> str:
    return json.dumps(engagement.reactions, ensure_ascii=False)


def parse_reactions_json(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {str(k): int(v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def post_is_recent(post: Post, hours: float = 1.0) -> bool:
    if not post.published_at:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    published = post.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published >= cutoff


def post_needs_comment_check(
    post: Post,
    stored_comment_count: int | None,
    hours: float = 1.0,
) -> bool:
    if post_is_recent(post, hours=hours):
        return True
    if stored_comment_count is None:
        return post.comment_count > 0
    return post.comment_count > stored_comment_count
