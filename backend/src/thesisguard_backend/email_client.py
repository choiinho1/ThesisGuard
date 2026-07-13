"""SMTP email sending. EMAIL_DRY_RUN=true (default) just logs instead of sending,
so local development never needs real SMTP credentials."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from thesisguard_backend.config import get_settings

logger = logging.getLogger(__name__)


def _send_sync(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username and settings.smtp_password:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


async def send_email(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    if settings.email_dry_run:
        logger.info("EMAIL_DRY_RUN — to=%s subject=%s\n%s", to_email, subject, body)
        return
    await asyncio.to_thread(_send_sync, to_email, subject, body)
