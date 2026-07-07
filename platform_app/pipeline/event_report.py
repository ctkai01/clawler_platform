from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

import httpx

from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# One entry per "sự vụ" (topic-event) report this platform can generate.
# Adding a new event report is adding a dict entry here (+ a route that
# passes its key) — no schema change needed.
EVENT_DEFINITIONS: dict[str, dict] = {
    "5g_mobifone": {"label": "5G", "match_terms": ["5g"]},
}

# "Mức độ tiếp cận" for news sources is a fixed property of the outlet, not
# something that varies article-to-article — a static lookup avoids an LLM
# call whose answer would never change for a known source.
REACH_TIER_BY_SOURCE = {
    "VnExpress": "Báo điện tử lớn – lượng truy cập cao",
    "Tuoi Tre": "Báo điện tử lớn – lượng truy cập cao",
    "Thanh Nien": "Báo điện tử lớn – lượng truy cập cao",
}
_DEFAULT_REACH_TIER = "Trang thông tin điện tử – lượng truy cập trung bình"

_SENTIMENTS = ("positive", "negative", "neutral")
_IMPACT_LEVELS = ("Cao", "Trung bình", "Thấp")

_COMPETITOR_BRAND_MAP = {
    "viettel": "Viettel",
    "vinaphone": "VinaPhone",
    "vina phone": "VinaPhone",
    "vietnamobile": "Vietnamobile",
    "gmobile": "Gmobile",
}


def _normalize_competitor_brand(term: str) -> str:
    return _COMPETITOR_BRAND_MAP.get(term.strip().lower(), term.strip().title())


def get_competitor_brands(organization_id: int) -> list[str]:
    """Distinct, display-normalized competitor brand names for this org
    (e.g. 'viettel'/'Viettel' both -> 'Viettel') — used so the report always
    shows one table per known competitor, even on a day with zero matches,
    instead of silently omitting the section."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT kc.term FROM organization_keywords ok
            JOIN keywords_catalog kc ON kc.id = ok.keyword_id
            WHERE ok.organization_id = %s AND kc.category = 'competitor' AND kc.is_active
            """,
            (organization_id,),
        ).fetchall()
    seen: list[str] = []
    for row in rows:
        brand = _normalize_competitor_brand(row["term"])
        if brand not in seen:
            seen.append(brand)
    return seen


def _api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY")


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _assess_article(content: str, brand: str, org_name: str) -> dict:
    """One LLM call per matched (document, brand) pair — sentiment + impact
    need to understand the content, unlike reach tier which is a fixed
    property of the source."""
    if not _api_key():
        return {"sentiment": "neutral", "impact_level": "Thấp", "reasoning": "OPENAI_API_KEY chưa cấu hình"}

    system_prompt = (
        f"Bạn là chuyên viên phân tích truyền thông của {org_name}. Đánh giá 1 bài viết/bài báo "
        f"nói về '{brand}' liên quan đến 5G. "
        'Trả lời CHỈ bằng JSON: {"sentiment": "positive|negative|neutral", '
        '"impact_level": "Cao|Trung bình|Thấp", "reasoning": "..."} '
        "(impact_level: Cao = ảnh hưởng lớn tới hình ảnh thương hiệu, Thấp = tin tức thông thường)."
    )
    try:
        resp = httpx.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": _model(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (content or "")[:4000]},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        logger.exception("Đánh giá bài viết bằng LLM thất bại (brand=%s)", brand)
        return {"sentiment": "neutral", "impact_level": "Thấp", "reasoning": "Lỗi khi gọi LLM"}

    sentiment = parsed.get("sentiment")
    if sentiment not in _SENTIMENTS:
        sentiment = "neutral"
    impact_level = parsed.get("impact_level")
    if impact_level not in _IMPACT_LEVELS:
        impact_level = "Thấp"
    return {"sentiment": sentiment, "impact_level": impact_level, "reasoning": parsed.get("reasoning") or ""}


def run_event_match(
    event_key: str, organization_id: int, period_start: datetime, period_end: datetime
) -> list[dict]:
    """Finds this org's documents (news + social alike) published in the
    window that mention the event's match_terms AND at least one tracked
    brand (the org's own DB-curated brand/competitor keywords — reusing that
    list instead of entity_gazetteer avoids re-solving the too-generic-term
    problem for a second naming scheme). One (document, brand) pair is
    LLM-assessed once and cached in event_report_matches; re-running the
    same window just reads the cached rows back."""
    event = EVENT_DEFINITIONS[event_key]
    event_patterns = [re.compile(r"\b" + re.escape(fold(t)) + r"\b", re.IGNORECASE) for t in event["match_terms"]]

    with get_pool().connection() as conn:
        org_row = conn.execute("SELECT name FROM organizations WHERE id = %s", (organization_id,)).fetchone()
        org_name = org_row["name"] if org_row else "MobiFone"

        kw_rows = conn.execute(
            """
            SELECT kc.category, kc.term FROM organization_keywords ok
            JOIN keywords_catalog kc ON kc.id = ok.keyword_id
            WHERE ok.organization_id = %s AND kc.category IN ('brand', 'competitor') AND kc.is_active
            """,
            (organization_id,),
        ).fetchall()
        brand_patterns: list[tuple[str, re.Pattern]] = []
        for row in kw_rows:
            brand = org_name if row["category"] == "brand" else _normalize_competitor_brand(row["term"])
            brand_patterns.append((brand, re.compile(r"\b" + re.escape(fold(row["term"])) + r"\b", re.IGNORECASE)))

        docs = conn.execute(
            """
            SELECT d.id, d.topic, d.content, d.url, d.author, d.platform_type, d.published_at,
                   COALESCE(d.reaction_count, 0) + COALESCE(d.comment_count, 0) + COALESCE(d.share_count, 0) AS engagement_total,
                   ct.display_name AS target_name
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE ct.organization_id = %s AND d.published_at >= %s AND d.published_at <= %s
            """,
            (organization_id, period_start, period_end),
        ).fetchall()

        results: list[dict] = []
        for doc in docs:
            text = fold(f"{doc['topic'] or ''} {doc['content'] or ''}")
            if not any(p.search(text) for p in event_patterns):
                continue
            matched_brands = {brand for brand, pattern in brand_patterns if pattern.search(text)}
            if not matched_brands:
                continue

            for brand in matched_brands:
                existing = conn.execute(
                    """
                    SELECT sentiment, impact_level, reasoning, handling_status
                    FROM event_report_matches WHERE document_id = %s AND event_key = %s AND brand = %s
                    """,
                    (doc["id"], event_key, brand),
                ).fetchone()
                if existing is None:
                    assessment = _assess_article(doc["content"] or doc["topic"] or "", brand, org_name)
                    conn.execute(
                        """
                        INSERT INTO event_report_matches (document_id, event_key, brand, sentiment, impact_level, reasoning)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, event_key, brand) DO NOTHING
                        """,
                        (doc["id"], event_key, brand, assessment["sentiment"], assessment["impact_level"], assessment["reasoning"]),
                    )
                    sentiment, impact_level, reasoning, handling_status = (
                        assessment["sentiment"],
                        assessment["impact_level"],
                        assessment["reasoning"],
                        "chua_xu_ly",
                    )
                else:
                    sentiment = existing["sentiment"]
                    impact_level = existing["impact_level"]
                    reasoning = existing["reasoning"]
                    handling_status = existing["handling_status"]

                results.append(
                    {
                        "document_id": doc["id"],
                        "brand": brand,
                        "topic": doc["topic"],
                        "content": doc["content"],
                        "url": doc["url"],
                        "author": doc["author"],
                        "platform_type": doc["platform_type"],
                        "published_at": doc["published_at"],
                        "engagement_total": doc["engagement_total"],
                        "target_name": doc["target_name"],
                        "sentiment": sentiment,
                        "impact_level": impact_level,
                        "reasoning": reasoning,
                        "handling_status": handling_status,
                        "reach_tier": (
                            REACH_TIER_BY_SOURCE.get(doc["target_name"], _DEFAULT_REACH_TIER)
                            if doc["platform_type"] == "news"
                            else None
                        ),
                    }
                )

    return results


def generate_overview_narrative(org_name: str, news_matches: list[dict]) -> str:
    """The "Đánh giá chung" paragraph — a second, separate LLM call that
    synthesizes the day's news-only matches into a written comparison across
    brands, rather than per-document classification."""
    if not news_matches:
        return f"Không có tin tức nào về 5G {org_name} hoặc đối thủ trong khoảng thời gian này."
    if not _api_key():
        return "Chưa cấu hình OPENAI_API_KEY nên không thể sinh đánh giá tổng quan tự động."

    by_brand: dict[str, list[dict]] = {}
    for m in news_matches:
        by_brand.setdefault(m["brand"], []).append(m)

    lines = []
    for brand, matches in by_brand.items():
        lines.append(f"--- {brand} ({len(matches)} bài) ---")
        for m in matches[:10]:
            lines.append(f"[{m['target_name']}] {m['topic']}: {(m['content'] or '')[:400]}")

    system_prompt = (
        f"Bạn là chuyên viên phân tích truyền thông của {org_name}. Dựa trên danh sách tin tức về 5G "
        f"của {org_name} và các đối thủ dưới đây, viết một đoạn 'Đánh giá chung' theo phong cách báo cáo "
        "nội bộ: 1 đoạn tổng quan ngắn, sau đó liệt kê nhận định riêng cho từng thương hiệu (mỗi thương hiệu "
        "1-2 gạch đầu dòng). Viết bằng tiếng Việt, khách quan, súc tích, không thêm số liệu không có trong dữ liệu."
    )
    try:
        resp = httpx.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": _model(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(lines)[:12000]},
                ],
                "temperature": 0.3,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Sinh đánh giá tổng quan bằng LLM thất bại")
        return "Không thể sinh đánh giá tổng quan tự động (lỗi khi gọi LLM)."
