from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
)
mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"
)


class EmailNotConfigured(RuntimeError):
    pass


# Always CC'd on every report email (manual "Gửi email ngay" and the
# automated daily job) on top of whatever the org configured in Settings —
# intentionally not exposed via the Settings API/UI, so it can't be removed
# by an org admin and doesn't clutter the org's own CC list.
_ALWAYS_CC = [
    "lainam113201@gmail.com",
    "quyda3822@gmail.com",
    "tommysnu@gmail.com",
    "ntt1102@gmail.com",
    "linhhubt.nd@gmail.com",
]


def _smtp_config() -> tuple[str, int, str, str, str]:
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM", user or "")
    if not host or not user or not password:
        raise EmailNotConfigured("SMTP_HOST/SMTP_USER/SMTP_PASSWORD chưa được cấu hình")
    port = int(os.environ.get("SMTP_PORT", "587"))
    return host, port, user, password, from_addr


def send_email_with_attachment(
    *,
    to: str,
    cc: list[str] | None,
    subject: str,
    body_text: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> None:
    """SMTP with STARTTLS on `SMTP_PORT` (default 587) — matches Gmail/most
    transactional providers. Raises EmailNotConfigured if env vars are
    missing, or smtplib's own exceptions on send failure — caller decides
    how to handle (the daily-report DAG logs and moves to the next org
    rather than failing the whole run)."""
    host, port, user, password, from_addr = _smtp_config()

    all_cc = [e for e in dict.fromkeys([*(cc or []), *_ALWAYS_CC]) if e != to]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    if all_cc:
        msg["Cc"] = ", ".join(all_cc)
    msg.set_content(body_text)
    content_type, _ = mimetypes.guess_type(attachment_filename)
    maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
    msg.add_attachment(
        attachment_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=attachment_filename,
    )

    recipients = [to, *all_cc]
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg, to_addrs=recipients)
    logger.info("Đã gửi email báo cáo tới %s (cc=%s)", to, all_cc)
