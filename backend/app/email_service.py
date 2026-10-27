from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from sqlalchemy.orm import Session

from .crypto import decrypt_optional
from .system_service import ensure_system_settings

logger = logging.getLogger("oxidized_ui.email")


def recipients(db: Session) -> list[str]:
    row = ensure_system_settings(db)
    return [item.strip() for item in (row.report_email_to or "").split(",") if item.strip()]


def configured(db: Session) -> bool:
    row = ensure_system_settings(db)
    return bool(row.smtp_host and row.smtp_from)


def send(
    db: Session,
    *,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    to: list[str] | None = None,
) -> bool:
    row = ensure_system_settings(db)
    if not configured(db):
        return False
    targets = to or recipients(db)
    if not targets:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = row.smtp_from
    message["To"] = ", ".join(targets)
    message.set_content(body)
    for filename, payload, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        message.add_attachment(
            payload,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=filename,
        )
    try:
        context = ssl.create_default_context()
        if row.smtp_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                row.smtp_host, int(row.smtp_port or 465), timeout=15, context=context
            )
        else:
            client = smtplib.SMTP(row.smtp_host, int(row.smtp_port or 587), timeout=15)
        with client:
            if row.smtp_tls and not row.smtp_ssl:
                client.starttls(context=context)
            password = decrypt_optional(row.smtp_password_ciphertext)
            if row.smtp_user and password:
                client.login(row.smtp_user, password)
            client.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 - email must never break reports
        logger.warning("SMTP delivery failed: %s", exc)
        return False


def status(db: Session) -> dict[str, Any]:
    row = ensure_system_settings(db)
    return {
        "configured": configured(db),
        "host": row.smtp_host,
        "port": row.smtp_port,
        "user": row.smtp_user,
        "from": row.smtp_from,
        "tls": row.smtp_tls,
        "ssl": row.smtp_ssl,
        "has_password": bool(row.smtp_password_ciphertext),
        "recipients": row.report_email_to,
    }
