"""Transactional e-mails through the Brevo API (https://developers.brevo.com/reference/sendtransacemail).

Settings (environment variables, read at send time):
- BREVO_API_KEY: the API key (a Secret Manager secret in GCP). Without it no e-mail can be sent, and
  e-mail confirmation is off unless EMAIL_VERIFICATION says otherwise.
- MAIL_FROM: sender address, on a domain authenticated in Brevo (SPF / DKIM), e.g. no-reply@seeingthesky.com.
- MAIL_FROM_NAME: sender name (default "Seeing AROME").
- PUBLIC_URL: base URL of the site for the links in the e-mails (default https://seeingthesky.com).
"""

import html
import json
import logging
import os
import urllib.request

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
logger = logging.getLogger(__name__)


def public_url() -> str:
    return os.environ.get("PUBLIC_URL", "https://seeingthesky.com").rstrip("/")


def send_mail(to: str, subject: str, text: str, link: str, link_label: str) -> bool:
    """Send one e-mail (plain text plus a simple HTML version with a button). False on failure (logged
    without the recipient's address)."""
    key = os.environ.get("BREVO_API_KEY", "")
    sender = os.environ.get("MAIL_FROM", "")
    if not key or not sender:
        logger.error("E-mail not sent: BREVO_API_KEY or MAIL_FROM is not set")
        return False
    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in text.split("\n\n") if p.strip() and link not in p)
    body = {
        "sender": {"email": sender, "name": os.environ.get("MAIL_FROM_NAME", "Seeing AROME")},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
        "htmlContent": (
            f'<div style="font-family:sans-serif;max-width:520px">{paragraphs}'
            f'<p><a href="{html.escape(link)}" style="display:inline-block;padding:10px 16px;background:#2d6cdf;'
            f'color:#fff;border-radius:8px;text-decoration:none">{html.escape(link_label)}</a></p>'
            f'<p style="font-size:12px;color:#666">{html.escape(link)}</p></div>'
        ),
    }
    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(body).encode(),
        headers={"api-key": key, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https URL
            return 200 <= r.status < 300
    except Exception as exc:  # network error or HTTP error status
        logger.error("E-mail not sent: %s", type(exc).__name__)
        return False
