"""
services/email/smtp_service.py
OSS replacement for SendGrid.
Dev:  Mailhog  (localhost:1025, no auth) — catches all outbound mail in browser UI
Prod: Postfix relay or any SMTP server (Mailu, Stalwart, etc.)
"""
from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog
from jinja2 import BaseLoader, Environment

from app.config import settings

logger = structlog.get_logger(__name__)

_TEMPLATES: dict[str, tuple[str, str]] = {
    "verify_email": (
        "Verify your PrivacyShield email",
        "<h2>Welcome!</h2><p><a href='{{ link }}'>Verify your email</a> (expires 24h).</p>",
    ),
    "scan_complete": (
        "Privacy scan complete — score {{ score }}/100",
        "<p>Risk level: <strong>{{ risk }}</strong>. <a href='{{ link }}'>View full report →</a></p>",
    ),
    "removal_submitted": (
        "Removal request submitted for {{ domain }}",
        "<p>Your opt-out for <strong>{{ domain }}</strong> has been filed. Expected: {{ days }} days.</p>",
    ),
    "password_reset": (
        "Reset your PrivacyShield password",
        "<p><a href='{{ link }}'>Reset password</a> (expires 1h). If you didn't request this, ignore.</p>",
    ),
}

_jinja = Environment(loader=BaseLoader(), autoescape=True)


async def send_email(to: str, template_name: str, context: dict) -> bool:
    """Send a transactional email. Returns True on success."""
    subj_tpl, body_tpl = _TEMPLATES.get(template_name, ("PrivacyShield", "<p>Notification</p>"))

    msg = MIMEMultipart("alternative")
    msg["Subject"] = _jinja.from_string(subj_tpl).render(**context)
    msg["From"] = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
    msg["To"] = to
    msg.attach(MIMEText(_jinja.from_string(body_tpl).render(**context), "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_USE_TLS,
            start_tls=settings.SMTP_STARTTLS,
        )
        logger.info("Email sent", to=to, template=template_name)
        return True
    except Exception as exc:
        logger.error("Email failed", to=to, error=str(exc))
        return False
