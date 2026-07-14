from __future__ import annotations

import logging

import httpx

from platform_app.pipeline.event_report import OPENAI_API_URL, _api_key, _model

logger = logging.getLogger(__name__)


def summarize_brand_bullets(brands: list[str], sentiment_label: str, docs_by_brand: dict[str, list[dict]]) -> str:
    """1 lệnh gọi LLM DUY NHẤT tóm tắt nội dung {sentiment_label} chính của
    CẢ 3 brand cùng lúc (mỗi brand 1 gạch đầu dòng) — gộp theo đúng pattern
    generate_overview_narrative (event_report.py), tránh gọi riêng từng
    brand (tốn 3 lần LLM thay vì 1). Brand nào không có bài nào thì không
    gọi LLM đoán, ghi cố định 'không có dữ liệu'."""
    brands_with_docs = [b for b in brands if docs_by_brand.get(b)]
    if not brands_with_docs:
        return "\n".join(f"- {b}: không có dữ liệu {sentiment_label} trong tuần này." for b in brands)
    if not _api_key():
        return "\n".join(
            f"- {b}: chưa cấu hình OPENAI_API_KEY nên không thể tóm tắt tự động." for b in brands_with_docs
        )

    lines = []
    for brand in brands_with_docs:
        docs = docs_by_brand[brand]
        lines.append(f"--- {brand} ({len(docs)} bài) ---")
        for d in docs[:10]:
            lines.append(f"[{d['target_name']}] {d['topic']}: {(d['content'] or '')[:400]}")

    system_prompt = (
        f"Bạn là chuyên viên phân tích truyền thông ngành viễn thông. Dựa CHỈ trên danh sách bài viết "
        f"{sentiment_label} dưới đây của từng nhà mạng, viết đúng 1 gạch đầu dòng cho MỖI nhà mạng có trong "
        f"danh sách, theo mẫu '- {{Tên nhà mạng}} có {{số bài}} bài, nội dung chủ yếu là ...'. "
        f"Chỉ liệt kê các nhà mạng sau: {', '.join(brands_with_docs)} — không thêm nhà mạng nào khác. "
        "Viết bằng tiếng Việt, khách quan, súc tích, không thêm chi tiết/sự kiện không có trong dữ liệu."
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
        summary = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Tóm tắt bullet %s theo nhà mạng bằng LLM thất bại", sentiment_label)
        summary = "\n".join(f"- {b}: không thể tóm tắt tự động (lỗi khi gọi LLM)." for b in brands_with_docs)

    missing = [b for b in brands if b not in brands_with_docs]
    if missing:
        summary += "\n" + "\n".join(f"- {b}: không có dữ liệu {sentiment_label} trong tuần này." for b in missing)
    return summary
