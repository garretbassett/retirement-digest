"""
News source fetchers — NewsAPI and RSS feeds, with AI relevance filtering.
"""

import json
import os
import logging
from datetime import datetime, timedelta, timezone

import requests
import feedparser
from openai import OpenAI

from config import (
    get_llm_config,
    NEWSAPI_BASE_URL,
    NEWSAPI_LANGUAGE,
    NEWSAPI_SORT_BY,
    NEWSAPI_PAGE_SIZE,
)

logger = logging.getLogger(__name__)


def fetch_newsapi_articles(query: str, api_key: str) -> list[dict]:
    """Fetch articles from NewsAPI for a given query."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    params = {
        "q": query,
        "from": yesterday,
        "to": today,
        "language": NEWSAPI_LANGUAGE,
        "sortBy": NEWSAPI_SORT_BY,
        "pageSize": NEWSAPI_PAGE_SIZE,
        "apiKey": api_key,
    }

    try:
        resp = requests.get(NEWSAPI_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("articles", []):
            # Skip removed/placeholder articles
            if item.get("title") in ("[Removed]", None):
                continue
            articles.append(
                {
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", {}).get("name", "Unknown"),
                    "published_at": item.get("publishedAt", ""),
                    "image_url": item.get("urlToImage", ""),
                }
            )
        return articles

    except requests.RequestException as e:
        logger.warning("NewsAPI request failed for query '%s': %s", query, e)
        return []


def fetch_rss_articles(feed_url: str) -> list[dict]:
    """Fetch recent articles from an RSS feed."""
    try:
        feed = feedparser.parse(feed_url)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        articles = []

        for entry in feed.entries[:10]:
            # Try to parse the published date
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                entry_date = datetime(*published[:6], tzinfo=timezone.utc)
                if entry_date < yesterday:
                    continue

            articles.append(
                {
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "source": feed.feed.get("title", "RSS Feed"),
                    "published_at": entry.get("published", ""),
                    "image_url": "",
                }
            )
        return articles

    except Exception as e:
        logger.warning("RSS fetch failed for '%s': %s", feed_url, e)
        return []


def filter_relevant_articles(articles: list[dict]) -> list[dict]:
    """
    Use Groq to filter out articles that aren't relevant to a 60+ retirement audience.
    Screens all articles in one API call for efficiency.
    """
    if not articles:
        return articles

    cfg = get_llm_config()
    if not cfg["api_key"]:
        logger.warning("No LLM API key set — skipping AI relevance filter")
        return articles

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    # Build the article list for the prompt
    article_list = ""
    for i, article in enumerate(articles, 1):
        article_list += (
            f"{i}. \"{article['title']}\" — {(article.get('description') or 'No description')[:150]}\n"
        )

    prompt = f"""You are a strict editorial filter for a daily email digest aimed at adults aged 60+ 
who care about having a secure and fulfilling retirement.

INCLUDE articles about:
- Retirement finances: Social Security, Medicare, pensions, 401k, IRA, savings, taxes in retirement
- Investing for retirees: stocks, bonds, dividends, portfolio strategy, market impacts on retirees
- Legislation that directly affects retirees or retirement benefits
- Health and wellness specifically relevant to older adults (exercise, aging research, longevity)
- Working in retirement, age discrimination, encore careers
- Intergenerational family dynamics (grandparenting, caregiving, wealth transfer)
- Cost of living, inflation impacts on fixed incomes

REJECT articles about:
- General news, politics, or legislation NOT directly tied to retirement or seniors
- Sports, entertainment, celebrities (unless directly about retirement topics)
- Corporate earnings or business news (unless directly about retirement funds/pensions)
- Crime, accidents, obituaries
- Technology news (unless it directly helps retirees)
- Anything that a 60+ retiree would look at and say "why is this in my retirement digest?"

Here are the articles to screen:
{article_list}

Return a JSON object with a "keep" key containing an array of the article numbers (1-based) 
that should be INCLUDED. Only include articles that clearly belong in a retirement digest.
Return ONLY valid JSON."""

    try:
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)
        keep_indices = set(parsed.get("keep", []))

        filtered = [a for i, a in enumerate(articles, 1) if i in keep_indices]
        removed_count = len(articles) - len(filtered)
        if removed_count > 0:
            logger.info(
                "AI filter: kept %d articles, removed %d irrelevant",
                len(filtered),
                removed_count,
            )
        return filtered

    except Exception as e:
        logger.error("AI relevance filter failed: %s — keeping all articles", e)
        return articles


def gather_articles(topics: dict) -> dict[str, list[dict]]:
    """
    Gather articles for all topics from all sources.
    Returns a dict mapping topic_key -> list of article dicts.
    """
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        logger.warning(
            "NEWS_API_KEY not set — skipping NewsAPI. Only RSS feeds will be used."
        )

    all_articles: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()

    for topic_key, topic_config in topics.items():
        topic_articles: list[dict] = []

        # NewsAPI queries
        if api_key:
            for query in topic_config.get("queries", []):
                results = fetch_newsapi_articles(query, api_key)
                for article in results:
                    if article["url"] and article["url"] not in seen_urls:
                        seen_urls.add(article["url"])
                        topic_articles.append(article)

        # RSS feeds (trusted sources)
        for feed_url in topic_config.get("rss_feeds", []):
            results = fetch_rss_articles(feed_url)
            for article in results:
                if article["url"] and article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    topic_articles.append(article)

        all_articles[topic_key] = topic_articles
        logger.info(
            "Topic '%s': found %d articles (pre-filter)",
            topic_config["name"],
            len(topic_articles),
        )

    # Run AI relevance filter across all articles per topic
    logger.info("🔍 Running AI relevance filter...")
    for topic_key in all_articles:
        all_articles[topic_key] = filter_relevant_articles(all_articles[topic_key])

    return all_articles
