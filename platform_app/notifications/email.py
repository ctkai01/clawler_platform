from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class EmailNotConfigured(RuntimeError):
    pass


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

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.set_content(body_text)
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=attachment_filename,
    )

    recipients = [to, *(cc or [])]
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg, to_addrs=recipients)
    logger.info("Đã gửi email báo cáo tới %s (cc=%s)", to, cc)
