from __future__ import annotations

import csv
import json
import logging
import os
import re
from pathlib import Path

import httpx

from platform_app.db.pool import get_pool
from platform_app.pipeline.settings import get_classify_mode
from platform_app.pipeline.text_normalize import fold

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
# gpt-4o-mini pricing as of writing: $0.15 / 1M input tokens, $0.60 / 1M output tokens.
_PRICE_PER_TOKEN_IN = 0.15 / 1_000_000
_PRICE_PER_TOKEN_OUT = 0.60 / 1_000_000
_MAX_IMAGES_PER_CALL = 3

CATEGORIES = ["khen_ngoi", "khieu_nai", "hoi_dap", "spam", "khac"]
SENTIMENTS = ["positive", "negative", "neutral"]

SYSTEM_PROMPT = (
    "Bạn phân loại bài viết/bình luận mạng xã hội tiếng Việt về viễn thông (Mobifone và đối thủ). "
    "Chọn đúng 1 category trong: khen_ngoi (khen dịch vụ), khieu_nai (phàn nàn/khiếu nại), "
    "hoi_dap (hỏi thông tin), spam (quảng cáo/spam), khac (không thuộc loại trên). "
    "Chọn đúng 1 sentiment trong: positive, negative, neutral. "
    "severity: 1=bình thường, 2=cần chú ý, 3=khẩn cấp (khủng hoảng truyền thông, khiếu nại nghiêm trọng). "
    'Trả lời CHỈ bằng JSON: {"category": "...", "sentiment": "...", "severity": 1, "reasoning": "..."}'
)

# "normal" mode: free, no LLM call — coarse keyword heuristics only. Meant as
# a zero-cost default, not a replacement for the LLM modes' accuracy.
_POSITIVE_WORDS = ["tốt", "hài lòng", "tuyệt vời", "cảm ơn", "ổn định", "ưng ý", "đáng tin", "nhanh chóng"]
_NEGATIVE_WORDS = [
    "tệ", "kém", "lỗi", "chậm", "khiếu nại", "thất vọng", "lừa đảo", "mất tiền",
    "không hài lòng", "trừ tiền", "bực", "tồi", "kém chất lượng",
]
_QUESTION_WORDS = ["?", "làm sao", "như thế nào", "cách nào", "ở đâu", "bao nhiêu", "có ai"]
_SPAM_WORDS = ["khuyến mãi", "giá chỉ", "đăng ký ngay", "liên hệ ngay", "inbox", "ib zalo", "hotline"]
_SEVERE_NEGATIVE_WORDS = ["lừa đảo", "mất tiền", "trừ tiền"]

# Fallback lexicon for when the small curated word lists above don't decide
# sentiment either way: 2678-word Vietnamese sentiment dataset (positive /
# negative / neutral, each with an "emphasis" sub-variant we collapse into
# the base 3 labels since we only need a majority-vote signal here).
_SENTIMENT_LEXICON_PATH = Path(__file__).resolve().parents[2] / "csv" / "dataset_1000_tu_khoa_cam_xuc.csv"
_SENTIMENT_LABEL_MAP = {
    "Tích cực": "positive",
    "Tích cực/Nhấn mạnh": "positive",
    "Tiêu cực": "negative",
    "Tiêu cực/Nhấn mạnh": "negative",
}
_sentiment_lexicon_cache: list[tuple[str, re.Pattern]] | None = None


def _load_sentiment_lexicon() -> list[tuple[str, re.Pattern]]:
    global _sentiment_lexicon_cache
    if _sentiment_lexicon_cache is not None:
        return _sentiment_lexicon_cache
    entries: list[tuple[str, re.Pattern]] = []
    with _SENTIMENT_LEXICON_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            word = (row.get("Từ tiếng Việt") or "").strip()
            label = _SENTIMENT_LABEL_MAP.get((row.get("Sắc thái/Nhóm") or "").strip())
            if not word or label is None:
                continue
            pattern = re.compile(r"\b" + re.escape(fold(word)) + r"\b", re.IGNORECASE)
            entries.append((label, pattern))
    _sentiment_lexicon_cache = entries
    return entries


def _lexicon_sentiment(folded_text: str) -> str | None:
    """Majority vote over lexicon hits. Returns None (stay neutral) on no
    hits or a positive/negative tie."""
    pos_hits = neg_hits = 0
    for label, pattern in _load_sentiment_lexicon():
        if pattern.search(folded_text):
            if label == "positive":
                pos_hits += 1
            else:
                neg_hits += 1
    if pos_hits > neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    return None


def _api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY")


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _classify_normal(text: str) -> dict:
    folded = fold(text)
    has_negative = any(w in folded for w in _NEGATIVE_WORDS)
    has_positive = any(w in folded for w in _POSITIVE_WORDS)
    has_question = any(w in folded for w in _QUESTION_WORDS)
    has_spam = any(w in folded for w in _SPAM_WORDS)

    if has_spam and not has_negative:
        category = "spam"
    elif has_negative:
        category = "khieu_nai"
    elif has_question:
        category = "hoi_dap"
    elif has_positive:
        category = "khen_ngoi"
    else:
        category = "khac"

    reasoning = "Phân loại rule-based theo từ khóa (mode normal, không gọi LLM)"
    if has_negative:
        sentiment = "negative"
    elif has_positive:
        sentiment = "positive"
    else:
        # Curated list didn't decide either way — fall back to the larger
        # sentiment-keyword dataset before defaulting to neutral.
        lexicon_sentiment = _lexicon_sentiment(folded)
        if lexicon_sentiment is not None:
            sentiment = lexicon_sentiment
            reasoning += "; sentiment suy ra từ bộ từ khóa cảm xúc mở rộng (dataset_1000_tu_khoa_cam_xuc.csv)"
        else:
            sentiment = "neutral"

    severity = 2 if any(w in folded for w in _SEVERE_NEGATIVE_WORDS) else 1

    return {
        "category": category,
        "sentiment": sentiment,
        "sentiment_source": "default",
        "severity": severity,
        "reasoning": reasoning,
        "cost_usd": 0.0,
    }


def _call_openai(content: list[dict] | str) -> dict:
    resp = httpx.post(
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {_api_key()}"},
        json={
            "model": _model(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    cost = (
        usage.get("prompt_tokens", 0) * _PRICE_PER_TOKEN_IN
        + usage.get("completion_tokens", 0) * _PRICE_PER_TOKEN_OUT
    )
    parsed = json.loads(data["choices"][0]["message"]["content"])
    category = parsed.get("category")
    if category not in CATEGORIES:
        category = "khac"
    sentiment = parsed.get("sentiment")
    if sentiment not in SENTIMENTS:
        sentiment = "neutral"
    return {
        "category": category,
        "sentiment": sentiment,
        "sentiment_source": "ai",
        "severity": int(parsed.get("severity") or 1),
        "reasoning": parsed.get("reasoning"),
        "cost_usd": cost,
    }


def _classify_llm_text(text: str) -> dict:
    return _call_openai(text[:4000])


def _classify_llm_image(text: str, images: list[str]) -> dict:
    content: list[dict] = [{"type": "text", "text": text[:4000]}]
    for url in images[:_MAX_IMAGES_PER_CALL]:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return _call_openai(content)


def _classify_rows(conn, rows: list[dict], mode: str) -> tuple[int, int]:
    completed = failed = 0
    for row in rows:
        text = f"{row['topic'] or ''}\n{row['content'] or ''}".strip()
        try:
            if mode == "normal":
                result = _classify_normal(text)
            elif mode == "llm_image" and row.get("images"):
                result = _classify_llm_image(text, row["images"])
            else:
                result = _classify_llm_text(text)
        except Exception:
            logger.exception("Classify thất bại cho document id=%s", row["id"])
            conn.execute(
                "UPDATE documents SET classification_status = 'failed' WHERE id = %s",
                (row["id"],),
            )
            failed += 1
            continue

        conn.execute(
            """
            UPDATE documents SET
                classification_status = 'completed',
                classification_category = %s,
                classification_sentiment = %s,
                classification_sentiment_source = %s,
                classification_severity = %s,
                classification_reasoning = %s,
                classification_cost_usd = classification_cost_usd + %s
            WHERE id = %s
            """,
            (
                result["category"],
                result["sentiment"],
                result["sentiment_source"],
                result["severity"],
                result["reasoning"],
                result["cost_usd"],
                row["id"],
            ),
        )
        completed += 1
    return completed, failed


def run_classify(
    *,
    batch_size: int = 20,
    document_ids: list[int] | None = None,
    mode: str | None = None,
) -> dict:
    """Only runs on documents keyword_filter already flagged as 'matched' —
    that gate is what keeps LLM spend bounded. `document_ids` narrows to a
    specific set (used by tests, and for on-demand reclassification).

    `mode` explicitly overrides the configured classify_mode for this call
    only (used by tests and on-demand reclassification) — one flat batch
    across whatever `document_ids`/pending backlog matches, same as before.

    With no override (the normal scheduled-DAG call), each organization is
    classified separately using THAT org's own configured classify_mode
    (pipeline_settings — see the "Cài đặt" page), since orgs no longer share
    one global mode."""
    if mode is not None:
        if mode in ("llm_text", "llm_image") and not _api_key():
            logger.warning("OPENAI_API_KEY chưa cấu hình — bỏ qua bước classify (mode=%s)", mode)
            return {"completed": 0, "failed": 0, "skipped_no_key": True}

        select_cols = "id, topic, content" + (", images" if mode == "llm_image" else "")
        with get_pool().connection() as conn:
            if document_ids is not None:
                rows = conn.execute(
                    f"""
                    SELECT {select_cols} FROM documents
                    WHERE keyword_status = 'matched' AND classification_status = 'pending'
                      AND id = ANY(%s)
                    LIMIT %s
                    """,
                    (document_ids, batch_size),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT {select_cols} FROM documents
                    WHERE keyword_status = 'matched' AND classification_status = 'pending'
                    LIMIT %s
                    """,
                    (batch_size,),
                ).fetchall()
            completed, failed = _classify_rows(conn, rows, mode)
        return {"completed": completed, "failed": failed, "mode": mode}

    with get_pool().connection() as conn:
        org_ids = [
            r["organization_id"]
            for r in conn.execute(
                """
                SELECT DISTINCT ct.organization_id
                FROM documents d
                JOIN crawl_targets ct ON ct.id = d.target_id
                WHERE d.keyword_status = 'matched' AND d.classification_status = 'pending'
                """
            ).fetchall()
        ]

    completed = failed = 0
    skipped_orgs = 0
    modes_used: dict[str, int] = {}
    for org_id in org_ids:
        org_mode = get_classify_mode(org_id)
        if org_mode in ("llm_text", "llm_image") and not _api_key():
            logger.warning(
                "OPENAI_API_KEY chưa cấu hình — bỏ qua classify cho organization_id=%s (mode=%s)", org_id, org_mode
            )
            skipped_orgs += 1
            continue

        select_cols = "d.id, d.topic, d.content" + (", d.images" if org_mode == "llm_image" else "")
        with get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {select_cols}
                FROM documents d
                JOIN crawl_targets ct ON ct.id = d.target_id
                WHERE d.keyword_status = 'matched' AND d.classification_status = 'pending'
                  AND ct.organization_id IS NOT DISTINCT FROM %s
                LIMIT %s
                """,
                (org_id, batch_size),
            ).fetchall()
            c, f = _classify_rows(conn, rows, org_mode)
        completed += c
        failed += f
        modes_used[org_mode] = modes_used.get(org_mode, 0) + c + f

    return {
        "completed": completed,
        "failed": failed,
        "modes_used": modes_used,
        "skipped_no_key_orgs": skipped_orgs,
    }
