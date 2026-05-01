#!/usr/bin/env python3
"""
Retirement Daily Digest — main entry point.

Gathers news, summarizes it, generates YouTube ideas, and produces
an HTML email digest (sent via SMTP and saved locally).

Usage:
    python digest.py              # Full run: gather, summarize, email
    python digest.py --no-email   # Generate digest but don't send email
    python digest.py --preview    # Open the HTML output in your browser
"""

import argparse
import logging
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE importing config (which reads env vars at import time)
load_dotenv(Path(__file__).parent / ".env")

from config import (
    EMAIL_SUBJECT_TEMPLATE,
    MAX_ARTICLES_PER_TOPIC,
    MAX_TOTAL_ARTICLES,
    OUTPUT_DIR,
    TOPICS,
)
from emailer import render_email, send_email
from sources import gather_articles
from summarizer import generate_daily_overview, generate_youtube_ideas, summarize_articles
from youtube import gather_youtube_trends

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("digest")


def main():
    parser = argparse.ArgumentParser(description="Retirement Daily Digest")
    parser.add_argument(
        "--no-email", action="store_true", help="Skip sending the email"
    )
    parser.add_argument(
        "--preview", action="store_true", help="Open the digest in your browser"
    )
    args = parser.parse_args()

    # Validate required keys
    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        logger.error("Either GROQ_API_KEY or OPENAI_API_KEY is required.")
        sys.exit(1)

    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y-%m-%d")
    date_display = today.strftime("%A, %B %d, %Y")
    subject = EMAIL_SUBJECT_TEMPLATE.format(date=date_display)

    # ------------------------------------------------------------------
    # Step 1: Gather articles from all sources
    # ------------------------------------------------------------------
    logger.info("📰 Gathering articles...")
    raw_articles = gather_articles(TOPICS)

    # Trim to limits
    total_count = 0
    trimmed_articles: dict[str, list[dict]] = {}
    for topic_key, articles in raw_articles.items():
        remaining = MAX_TOTAL_ARTICLES - total_count
        if remaining <= 0:
            trimmed_articles[topic_key] = []
            continue
        limit = min(MAX_ARTICLES_PER_TOPIC, remaining)
        trimmed_articles[topic_key] = articles[:limit]
        total_count += len(trimmed_articles[topic_key])

    article_count = sum(len(a) for a in trimmed_articles.values())
    logger.info("📋 Collected %d articles across %d topics", article_count, len(TOPICS))

    if article_count == 0:
        logger.warning(
            "No articles found. Check your NEWS_API_KEY or try different queries."
        )
        # Still generate the digest with a "quiet day" message

    # ------------------------------------------------------------------
    # Step 2: Summarize articles per topic
    # ------------------------------------------------------------------
    logger.info("🤖 Summarizing articles...")
    topic_names = {key: cfg["name"] for key, cfg in TOPICS.items()}

    for topic_key, articles in trimmed_articles.items():
        if articles:
            trimmed_articles[topic_key] = summarize_articles(
                topic_names[topic_key], articles
            )

    # ------------------------------------------------------------------
    # Step 3: Generate daily overview
    # ------------------------------------------------------------------
    logger.info("📝 Writing daily overview...")
    overview = generate_daily_overview(trimmed_articles, topic_names)

    # ------------------------------------------------------------------
    # Step 4: Generate YouTube content ideas
    # ------------------------------------------------------------------
    logger.info("🎬 Generating YouTube content ideas...")
    youtube_ideas = generate_youtube_ideas(trimmed_articles, topic_names)

    # ------------------------------------------------------------------
    # Step 5: Gather YouTube trends
    # ------------------------------------------------------------------
    logger.info("📺 Gathering YouTube trends...")
    yt_trends = gather_youtube_trends()

    # ------------------------------------------------------------------
    # Step 6: Render the email
    # ------------------------------------------------------------------
    logger.info("✉️  Rendering email...")
    html = render_email(
        date_display=date_display,
        subject=subject,
        overview=overview,
        topics=trimmed_articles,
        topic_names=topic_names,
        youtube_ideas=youtube_ideas,
        yt_trends=yt_trends,
    )

    # Save locally
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"digest-{date_str}.html"
    output_file.write_text(html, encoding="utf-8")
    logger.info("💾 Saved to %s", output_file)

    # ------------------------------------------------------------------
    # Step 6: Send or preview
    # ------------------------------------------------------------------
    if args.preview:
        webbrowser.open(f"file://{output_file.resolve()}")
        logger.info("🌐 Opened in browser")

    if not args.no_email:
        logger.info("📧 Sending email...")
        sent = send_email(subject, html)
        if sent:
            logger.info("✅ Digest sent successfully!")
        else:
            logger.warning("⚠️  Email not sent (check settings). HTML saved locally.")
    else:
        logger.info("📧 Email skipped (--no-email flag)")

    logger.info("🎉 Done! Have a great day.")


if __name__ == "__main__":
    main()
