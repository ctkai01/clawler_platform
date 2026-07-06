from __future__ import annotations

import logging
from datetime import datetime, timezone

from platform_app.db.pool import get_pool
from platform_app.notifications.email import EmailNotConfigured, send_email_with_attachment

logger = logging.getLogger(__name__)


def send_daily_reports() -> dict:
    """Emails the daily report (Word .docx, same document as the manual "Xuất
    Word" button) to every organization that has configured+enabled a
    report-email recipient. The window is anchored to the schedule, not to
    actual execution time: it always covers 08:00 (Vietnam time) the previous
    day to 08:00 today, and the report/email is labeled with today's date —
    so a delayed Airflow run still produces the intended window instead of a
    window that rolls forward with it. One org failing (bad SMTP config, bad
    address, ...) must not stop the rest — same per-item error isolation as
    the forum/news crawlers."""
    from platform_app.api.routers.org import build_daily_word_report_bytes_between  # local import: avoid API<->pipeline import cycle at module load

    report_date = datetime.now(timezone.utc).date()

    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT ore.organization_id, ore.recipient_email, ore.cc_emails, o.name AS org_name
            FROM organization_report_email ore
            JOIN organizations o ON o.id = ore.organization_id
            WHERE ore.enabled AND ore.recipient_email IS NOT NULL AND ore.recipient_email != ''
            """
        ).fetchall()

    sent = failed = 0
    date_label = report_date.strftime("%d/%m/%Y")
    for row in rows:
        org_id = row["organization_id"]
        try:
            synthetic_user = {"organization_id": org_id, "role": "org_main", "accessible_target_ids": None}
            content = build_daily_word_report_bytes_between(synthetic_user, row["org_name"], report_date)
            send_email_with_attachment(
                to=row["recipient_email"],
                cc=row["cc_emails"],
                subject=f"[{row['org_name']}] Báo cáo mạng xã hội ngày {date_label}",
                body_text=(
                    f"Chào {row['org_name']},\n\n"
                    f"Đính kèm là báo cáo tổng hợp mạng xã hội ngày {date_label}.\n\n"
                    "Email này được gửi tự động, vui lòng không trả lời."
                ),
                attachment_bytes=content,
                attachment_filename=f"bao-cao-{report_date.strftime('%Y%m%d')}.docx",
            )
            sent += 1
        except EmailNotConfigured:
            logger.warning("SMTP chưa cấu hình — bỏ qua gửi report email cho organization_id=%s", org_id)
            failed += 1
        except Exception:
            logger.exception("Gửi report email thất bại cho organization_id=%s", org_id)
            failed += 1

    return {"sent": sent, "failed": failed}
