"""
AI-powered summarization and content idea generation using Groq (free tier).
Uses the OpenAI-compatible SDK pointed at Groq's API.
"""

import json
import logging
import os

from openai import OpenAI

from config import get_llm_config

logger = logging.getLogger(__name__)


def get_client() -> OpenAI:
    """Create an LLM client using the active provider."""
    cfg = get_llm_config()
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


def _model() -> str:
    return get_llm_config()["model"]


def summarize_articles(topic_name: str, articles: list[dict]) -> list[dict]:
    """
    Summarize a list of articles for a given topic.
    Returns the articles with an added 'summary' field.
    """
    if not articles:
        return articles

    client = get_client()

    # Build a prompt with all articles for this topic
    articles_text = ""
    for i, article in enumerate(articles, 1):
        articles_text += (
            f"\n--- Article {i} ---\n"
            f"Title: {article['title']}\n"
            f"Source: {article['source']}\n"
            f"Description: {article['description']}\n"
        )

    prompt = f"""You are writing for a daily email digest aimed at adults aged 60 and older 
who are interested in retirement-related topics. Your tone should be warm, clear, and 
informative — like a trusted friend who reads the news for you.

Topic: {topic_name}

Here are today's articles:
{articles_text}

For each article, write a 2-3 sentence summary that:
- Explains why this matters to someone who is retired or approaching retirement
- Uses plain language (no jargon)
- Highlights any action items or things to watch

Return your response as a JSON object with a "summaries" key containing an array.
Each element should have:
- "index": the article number (1-based)
- "summary": your 2-3 sentence summary

Return ONLY valid JSON, no other text."""

    try:
        response = client.chat.completions.create(
            model=_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        # Handle both {"summaries": [...]} and direct [...] formats
        summaries = parsed if isinstance(parsed, list) else parsed.get("summaries", [])

        for item in summaries:
            idx = item.get("index", 0) - 1
            if 0 <= idx < len(articles):
                articles[idx]["summary"] = item.get("summary", "")

    except Exception as e:
        logger.error("Summarization failed for topic '%s': %s", topic_name, e)
        # Fall back to using descriptions as summaries
        for article in articles:
            if "summary" not in article:
                article["summary"] = article.get("description", "No summary available.")

    # Ensure every article has a summary
    for article in articles:
        if "summary" not in article or not article["summary"]:
            article["summary"] = article.get("description", "No summary available.")

    return articles


def generate_daily_overview(all_topics: dict[str, list[dict]], topic_names: dict) -> str:
    """
    Generate an overall summary of the day's retirement news.
    """
    client = get_client()

    digest_text = ""
    for topic_key, articles in all_topics.items():
        if not articles:
            continue
        name = topic_names.get(topic_key, topic_key)
        digest_text += f"\n## {name}\n"
        for article in articles:
            digest_text += f"- {article['title']}: {article.get('summary', article.get('description', ''))}\n"

    if not digest_text.strip():
        return "It was a quiet day in retirement news. Check back tomorrow for updates."

    prompt = f"""You are the editor of a daily retirement news digest for adults 60+. 
Based on today's coverage, write a 3-4 paragraph overview that:

1. Opens with the biggest story or theme of the day
2. Connects the dots between different topics where relevant
3. Ends with an encouraging or forward-looking note
4. Uses a warm, conversational tone — like a morning coffee chat

Today's coverage:
{digest_text}

Write the overview in plain text (no markdown headers). Keep it under 250 words."""

    try:
        response = client.chat.completions.create(
            model=_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Overview generation failed: %s", e)
        return "Today's digest covers the latest in retirement news. See the topics below for details."


def generate_youtube_ideas(all_topics: dict[str, list[dict]], topic_names: dict) -> list[dict]:
    """
    Generate YouTube content ideas based on the day's news.
    Returns a list of dicts with 'title', 'hook', 'outline', and 'why' fields.
    """
    client = get_client()

    digest_text = ""
    for topic_key, articles in all_topics.items():
        if not articles:
            continue
        name = topic_names.get(topic_key, topic_key)
        digest_text += f"\n## {name}\n"
        for article in articles:
            digest_text += f"- {article['title']}\n"

    if not digest_text.strip():
        return []

    prompt = f"""You are a YouTube content strategist for a channel aimed at adults 60+ 
covering retirement, personal finance, health, and lifestyle topics.

Based on today's news headlines, suggest 3-5 YouTube video ideas that would:
- Be timely and relevant (tied to today's news)
- Appeal to viewers aged 60+
- Get clicks without being clickbait
- Be feasible for a solo creator to produce

Today's headlines:
{digest_text}

For each idea, provide:
- "title": A compelling YouTube title (under 60 chars)
- "hook": The first 15 seconds of the video — what you'd say to keep viewers watching
- "outline": 3-5 bullet points for the video structure
- "why": One sentence on why this would perform well today

Return as a JSON object with a "ideas" key containing the array."""

    try:
        response = client.chat.completions.create(
            model=_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)
        return parsed.get("ideas", [])

    except Exception as e:
        logger.error("YouTube idea generation failed: %s", e)
        return []
