from __future__ import annotations

import json
import logging

import httpx

from platform_app.pipeline.event_report import OPENAI_API_URL, _api_key, _model

logger = logging.getLogger(__name__)


def summarize_negative_theme(org_name: str, channel_label: str, docs: list[dict]) -> tuple[str, str | None]:
    """1-2 câu tóm tắt nội dung tiêu cực chính của 1 kênh (báo chí/mạng xã
    hội) trong tuần — dựa trên các tài liệu thật thuộc chủ đề tiêu cực phổ
    biến nhất kênh đó — cộng địa danh (nếu có) mà nội dung đó nhắc tới, dùng
    cho bảng "Điểm nóng". Trích địa danh trong CÙNG 1 lệnh gọi LLM với tóm
    tắt (không gọi thêm 1 lần riêng) để không tăng gấp đôi chi phí/độ trễ.
    Không gọi LLM nếu không có tài liệu nào (giống early-return của
    event_report.generate_overview_narrative)."""
    if not docs:
        return f"Không có phản ánh tiêu cực nào trên {channel_label} trong tuần này.", None
    if not _api_key():
        return (
            f"Chưa cấu hình OPENAI_API_KEY nên không thể tóm tắt tự động nội dung tiêu cực trên {channel_label}.",
            None,
        )

    lines = [f"[{d['target_name']}] {d['topic']}: {(d['content'] or '')[:400]}" for d in docs]

    system_prompt = (
        f"Bạn là chuyên viên phân tích truyền thông của {org_name}. Dựa CHỈ trên danh sách bài viết tiêu cực "
        f"về {org_name} trên {channel_label} dưới đây, trả lời CHỈ bằng JSON: "
        '{"summary": "1-2 câu tóm tắt nội dung tiêu cực chính đang được phản ánh", '
        '"location": "tên tỉnh/thành phố/quận huyện Việt Nam nếu nội dung có nhắc RÕ RÀNG, hoặc null nếu không '
        'nhắc tới địa điểm cụ thể nào"}. '
        "Viết summary bằng tiếng Việt, khách quan, súc tích, không thêm chi tiết/sự kiện không có trong dữ liệu. "
        "TUYỆT ĐỐI không đoán/suy luận địa điểm nếu nội dung không nói rõ — thà trả null còn hơn đoán sai."
    )
    try:
        resp = httpx.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": _model(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(lines)[:8000]},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        summary = (parsed.get("summary") or "").strip() or f"Không tóm tắt được nội dung tiêu cực trên {channel_label}."
        location = parsed.get("location")
        location = location.strip() if isinstance(location, str) and location.strip() else None
        return summary, location
    except Exception:
        logger.exception("Tóm tắt nội dung tiêu cực bằng LLM thất bại (channel=%s)", channel_label)
        return f"Không thể tóm tắt tự động nội dung tiêu cực trên {channel_label} (lỗi khi gọi LLM).", None


def generate_negative_overview_narrative(org_name: str, comparison: dict, news_theme: str, social_theme: str) -> str:
    """Mục 'Đánh giá chung' — 1 LLM call tổng hợp xu hướng số liệu thật +
    2 câu tóm tắt theme theo kênh, viết đoạn tổng quan + Kênh báo chí + Kênh
    mạng xã hội + Rủi ro (chỉ nếu có dấu hiệu đáng lo từ số liệu, không bịa
    sự kiện cụ thể) + Đề xuất (luôn có, hành động tương lai)."""
    if not _api_key():
        return "Chưa cấu hình OPENAI_API_KEY nên không thể sinh đánh giá tổng quan tự động."

    data_summary = (
        f"Tổng thông tin thu thập: tuần trước {comparison['total_prev']}, tuần này {comparison['total_this']}.\n"
        f"Tổng thông tin tiêu cực: tuần trước {comparison['negative_prev']}, tuần này {comparison['negative_this']}.\n"
        f"Tiêu cực trên kênh báo chí tuần này: {comparison['negative_news_this']}.\n"
        f"Tiêu cực trên kênh mạng xã hội tuần này: {comparison['negative_social_this']}.\n"
        f"Nội dung tiêu cực chính trên kênh báo chí: {news_theme}\n"
        f"Nội dung tiêu cực chính trên kênh mạng xã hội: {social_theme}"
    )

    system_prompt = (
        f"Bạn là chuyên viên phân tích truyền thông của {org_name}. Dựa CHỈ trên số liệu và tóm tắt dưới đây, "
        "viết mục 'Đánh giá chung' theo phong cách báo cáo nội bộ, theo đúng cấu trúc: "
        "1 đoạn tổng quan ngắn về xu hướng tiêu cực tuần này so với tuần trước; sau đó dòng tiêu đề 'Kênh báo chí:' "
        "kèm nhận xét ngắn; dòng tiêu đề 'Kênh mạng xã hội:' kèm nhận xét ngắn; NẾU số liệu cho thấy dấu hiệu đáng "
        "lo thật sự (tăng mạnh, dồn vào 1 chủ đề...) thì thêm dòng tiêu đề 'Rủi ro:' kèm 1-2 gạch đầu dòng — "
        "TUYỆT ĐỐI không bịa ra sự kiện cụ thể (như khủng hoảng truyền thông, tẩy chay...) không có trong dữ liệu; "
        "nếu không có dấu hiệu rủi ro rõ ràng thì BỎ HẲN mục 'Rủi ro'. Cuối cùng luôn có dòng tiêu đề 'Đề xuất:' "
        "kèm 1-3 gạch đầu dòng đề xuất hành động cho tương lai (không khẳng định là đã thực hiện). "
        "Viết bằng tiếng Việt, khách quan, súc tích, không thêm số liệu không có trong dữ liệu trên."
    )
    try:
        resp = httpx.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": _model(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": data_summary},
                ],
                "temperature": 0.3,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Sinh đánh giá tổng quan tiêu cực bằng LLM thất bại")
        return "Không thể sinh đánh giá tổng quan tự động (lỗi khi gọi LLM)."
