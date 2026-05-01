"""
Email rendering and sending via Resend.
"""

import logging
import os
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_FILE = "email_template.html"


def render_email(
    date_display: str,
    subject: str,
    overview: str,
    topics: dict[str, list[dict]],
    topic_names: dict[str, str],
    youtube_ideas: list[dict],
    yt_trends: Optional[dict] = None,
) -> str:
    """Render the HTML email from the Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template(TEMPLATE_FILE)

    # Split overview into paragraphs for nicer rendering
    overview_paragraphs = [p.strip() for p in overview.split("\n\n") if p.strip()]
    if not overview_paragraphs:
        overview_paragraphs = [overview]

    html = template.render(
        date_display=date_display,
        subject=subject,
        overview_paragraphs=overview_paragraphs,
        topics=topics,
        topic_names=topic_names,
        youtube_ideas=youtube_ideas,
        yt_trends=yt_trends,
    )
    return html


def send_email(subject: str, html_body: str) -> bool:
    """Send the digest email via Resend."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    email_from = os.environ.get("EMAIL_FROM", "")
    email_to = os.environ.get("EMAIL_TO", "")

    if not all([api_key, email_from, email_to]):
        logger.warning(
            "Email settings incomplete — skipping send. "
            "Set RESEND_API_KEY, EMAIL_FROM, and EMAIL_TO in .env"
        )
        return False

    resend.api_key = api_key

    to_list = [addr.strip() for addr in email_to.split(",")]

    # Add CC if configured
    cc_list = []
    email_cc = os.environ.get("EMAIL_CC", "")
    if email_cc:
        cc_list = [addr.strip() for addr in email_cc.split(",")]

    params = {
        "from": email_from,
        "to": to_list,
        "subject": subject,
        "html": html_body,
    }
    if cc_list:
        params["cc"] = cc_list

    try:
        result = resend.Emails.send(params)
        logger.info("Email sent (id: %s) to %s", result.get("id"), email_to)
        return True
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return False
