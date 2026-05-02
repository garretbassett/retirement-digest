"""
YouTube Data API integration — fetch trending retirement videos from the past week.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from openai import OpenAI

from config import (
    get_llm_config,
    YOUTUBE_API_BASE_URL,
    YOUTUBE_DAYS_BACK,
    YOUTUBE_MAX_RESULTS_PER_QUERY,
    YOUTUBE_MIN_VIEW_COUNT,
    YOUTUBE_SEARCH_QUERIES,
)

logger = logging.getLogger(__name__)

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


def _parse_duration(iso_duration: str) -> int:
    """Parse ISO 8601 duration (PT#H#M#S) to seconds."""
    import re

    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration
    )
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def fetch_youtube_videos(api_key: str) -> list[dict]:
    """
    Search YouTube for recent retirement-related videos with traction.
    Returns a deduplicated list of video dicts sorted by view count.
    """
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=YOUTUBE_DAYS_BACK)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    seen_ids: set[str] = set()
    all_videos: list[dict] = []

    for query in YOUTUBE_SEARCH_QUERIES:
        try:
            # Step 1: Search for videos
            search_params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "viewCount",
                "publishedAfter": published_after,
                "maxResults": YOUTUBE_MAX_RESULTS_PER_QUERY,
                "relevanceLanguage": "en",
                "key": api_key,
            }
            resp = requests.get(YOUTUBE_API_BASE_URL, params=search_params, timeout=15)
            resp.raise_for_status()
            search_data = resp.json()

            video_ids = []
            snippets = {}
            for item in search_data.get("items", []):
                vid_id = item["id"].get("videoId", "")
                if vid_id and vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    video_ids.append(vid_id)
                    snippets[vid_id] = item["snippet"]

            if not video_ids:
                continue

            # Step 2: Get view counts, duration, and language for these videos
            # Process in batches of 50 (API limit)
            for batch_start in range(0, len(video_ids), 50):
                batch_ids = video_ids[batch_start : batch_start + 50]
                stats_params = {
                    "part": "statistics,contentDetails,snippet,liveStreamingDetails",
                    "id": ",".join(batch_ids),
                    "key": api_key,
                }
                stats_resp = requests.get(
                    YOUTUBE_VIDEOS_URL, params=stats_params, timeout=15
                )
                stats_resp.raise_for_status()
                stats_data = stats_resp.json()

                for item in stats_data.get("items", []):
                    vid_id = item["id"]
                    stats = item.get("statistics", {})
                    view_count = int(stats.get("viewCount", 0))

                    if view_count < YOUTUBE_MIN_VIEW_COUNT:
                        continue

                    # Parse duration (ISO 8601: PT#M#S)
                    duration_iso = item.get("contentDetails", {}).get(
                        "duration", "PT0S"
                    )
                    duration_seconds = _parse_duration(duration_iso)
                    is_short = duration_seconds <= 60

                    # Detect livestreams
                    live_details = item.get("liveStreamingDetails", {})
                    is_livestream = bool(live_details.get("actualStartTime"))

                    if is_short:
                        vid_format = "Short"
                    elif is_livestream:
                        vid_format = "Livestream"
                    else:
                        vid_format = "Long"

                    # Get language
                    detail_snippet = item.get("snippet", {})
                    language = detail_snippet.get(
                        "defaultAudioLanguage",
                        detail_snippet.get("defaultLanguage", ""),
                    )
                    # Normalize to 2-letter code
                    if language:
                        language = language[:2].lower()

                    snippet = snippets.get(vid_id, {})
                    all_videos.append(
                        {
                            "video_id": vid_id,
                            "title": snippet.get("title", ""),
                            "channel": snippet.get("channelTitle", ""),
                            "description": snippet.get("description", "")[:300],
                            "published_at": snippet.get("publishedAt", ""),
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "thumbnail_url": f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                            "view_count": view_count,
                            "like_count": int(stats.get("likeCount", 0)),
                            "comment_count": int(stats.get("commentCount", 0)),
                            "duration_seconds": duration_seconds,
                            "is_short": is_short,
                            "format": vid_format,
                            "language": language or "unknown",
                        }
                    )

        except requests.RequestException as e:
            logger.warning("YouTube search failed for query '%s': %s", query, e)

    # Sort by view count descending, take top 100
    all_videos.sort(key=lambda v: v["view_count"], reverse=True)
    all_videos = all_videos[:100]

    logger.info(
        "YouTube: found %d trending videos (min %d views)",
        len(all_videos),
        YOUTUBE_MIN_VIEW_COUNT,
    )
    return all_videos


def analyze_youtube_trends(videos: list[dict]) -> dict:
    """
    Use Groq to analyze trending YouTube videos and produce:
    - A trend summary
    - Per-video: summary, why_performing, topic, angle, content_type
    Returns a dict with 'trend_summary' and 'videos' keys.
    """
    if not videos:
        return {"trend_summary": "", "videos": []}

    cfg = get_llm_config()
    if not cfg["api_key"]:
        logger.warning("No LLM API key set — skipping YouTube analysis")
        return {"trend_summary": "", "videos": videos}

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    model = cfg["model"]

    # --- Tag videos in batches of 25 ---
    batch_size = 25
    for batch_start in range(0, len(videos), batch_size):
        batch = videos[batch_start : batch_start + batch_size]
        video_list = ""
        for i, v in enumerate(batch, 1):
            video_list += (
                f"{i}. \"{v['title']}\" by {v['channel']}\n"
                f"   Views: {v['view_count']:,} | "
                f"Description: {(v.get('description') or '')[:200]}\n\n"
            )

        tag_prompt = f"""Analyze these YouTube videos about retirement/finance. For each video, provide:

- "index": video number (1-based within this batch)
- "summary": 1-2 sentence summary of what the video covers
- "why_performing": 1-2 sentence hypothesis about why it's getting views
- "topic": one of: Social Security, Medicare, Investing, Retirement Planning, Tax Strategy, Budgeting, Health & Wellness, Lifestyle, Career, Real Estate, Insurance, General Finance, Other
- "angle": one of: Educational, News Reaction, Personal Story, Fear/Urgency, Empowering, Listicle, How-To, Interview, Myth-Busting, Comparison, Other
- "content_type": one of: Explainer, Tutorial, Commentary, Vlog, Case Study, Q&A, Compilation, Motivational, Other
- "jtbd": an array of one or more labels from this list:
  - "Make Me Feel Better" — reduces stress/fear/uncertainty about money, reassures the viewer
  - "Explain a Concept" — turns complex financial systems into clear, usable frameworks
  - "Tell Me Where I'm At" — helps viewer understand where they stand relative to others (savings, income, lifestyle)
  - "Make a Decision For Me" — gives clear recommendations so viewer doesn't have to evaluate everything
  - "Help Me Feel Part of Something" — helps viewer adopt a financial worldview or feel part of a group
  - "Make Me Feel Worse" — uses fear, urgency, or alarm as the primary hook, frames situation as crisis

Tag based on what the title and description PROMISE to the viewer. A video can have multiple JTBD tags.

Videos:
{video_list}

Return a JSON object with a "videos" key containing the array. Return ONLY valid JSON."""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": tag_prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            analyses = parsed.get("videos", [])

            for item in analyses:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    batch[idx]["summary"] = item.get("summary", "")
                    batch[idx]["why_performing"] = item.get("why_performing", "")
                    batch[idx]["topic"] = item.get("topic", "Other")
                    batch[idx]["angle"] = item.get("angle", "Other")
                    batch[idx]["content_type"] = item.get("content_type", "Other")
                    batch[idx]["jtbd"] = item.get("jtbd", [])

        except Exception as e:
            logger.error("Video tagging failed for batch %d: %s", batch_start, e)

    # Ensure defaults
    for v in videos:
        v.setdefault("summary", (v.get("description") or "")[:150])
        v.setdefault("why_performing", "")
        v.setdefault("topic", "Other")
        v.setdefault("angle", "Other")
        v.setdefault("content_type", "Other")
        v.setdefault("jtbd", [])

    # --- Generate trend summary from top 20 ---
    top_list = ""
    for i, v in enumerate(videos[:20], 1):
        top_list += (
            f"{i}. \"{v['title']}\" — {v['topic']} / {v['angle']} / {v['content_type']} "
            f"({v['view_count']:,} views)\n"
        )

    trend_summary = ""
    try:
        trend_prompt = f"""You are analyzing trending YouTube videos about retirement for a content creator
who makes empowering, no-BS videos for adults 60+.

Here are the top 20 performing videos this week, tagged with topic, angle, and content type:

{top_list}

Write a 2-3 paragraph analysis covering:
1. What TOPICS are getting the most traction? What specific subjects are viewers drawn to?
2. What ANGLES and FORMATS are working? (e.g., are fear-based titles outperforming educational ones? Are explainers beating vlogs?)
3. What GAPS exist — topics or angles that aren't being covered but should be?

Write this as practical intelligence for a creator deciding what to make next. Be specific."""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": trend_prompt}],
            temperature=0.5,
        )
        trend_summary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Trend summary generation failed: %s", e)

    return {"trend_summary": trend_summary, "videos": videos}


def gather_youtube_trends() -> dict:
    """
    Main entry point: fetch videos and analyze them.
    Returns dict with 'trend_summary' and 'videos'.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY_2", "")
    if not api_key:
        logger.warning(
            "YOUTUBE_API_KEY_2 not set — skipping YouTube trends. "
            "Get a free key at https://console.cloud.google.com"
        )
        return {"trend_summary": "", "videos": []}

    videos = fetch_youtube_videos(api_key)
    return analyze_youtube_trends(videos)


# --- Competitor channel tracking ---

# Channel name -> YouTube channel ID
# To find a channel ID: go to the channel page, view source, search for "channelId"
COMPETITOR_CHANNELS = {
    "Azul Wells": "UCE-VsPf_vj8E-eXV9vU5GmA",
    "Root Financial": "UC8pFXyHfzI9jTtRQDQpS3Hw",
    "Parallel Wealth": "UCwY3ZvNc_qCU-WuIKh-aulA",
    "Holy Schmidt!": "UCl9IwlpNczNQllEfeIrzscQ",
    "Jazz Wealth Managers": "UCCFkdk7tmcgvgTe9G0lrmUA",
    "Rob Berger": "UC9C17-OMxa-7oRSaCtztObw",
    "Erin Talks Money": "UCpXipTyhIY9kprpvVd-lu0A",
    "James Conole": "UCTrsX03Mn3N3HU6Vnxi1_zA",
    "Streamline Financial": "UCJ-_I3IYY-nPzvg_gT7BO0Q",
    "Two Sides of FI": "UC4IeUR6mgNzxsfid_nKoe-w",
    "Our Rich Journey": "UCgjz9J571V634adHtbyb8JA",
    "Keep the Change": "UCc_ZMZlRFGhd1WKaZaV5GNw",
    "Mapped Out Money": "UCzuZJ-F3N2VfjQ8UmwulreA",
    "The Financial Diet": "UC2FAWBgLoW_DG2A3v32mgBA",
    "BeatTheBush": "UCcnyjTK4IheQN2ycsE7NZTQ",
    "Your Money, Your Wealth": "UC9VHZPrBHs-wbpg2V8gnZHw",
}


def fetch_competitor_videos(api_key: str) -> list[dict]:
    """Fetch recent videos from competitor channels (past 30 days)."""
    published_after_30d = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    all_videos: list[dict] = []

    for channel_name, channel_id in COMPETITOR_CHANNELS.items():
        try:
            search_params = {
                "part": "snippet",
                "channelId": channel_id,
                "type": "video",
                "order": "date",
                "publishedAfter": published_after_30d,
                "maxResults": 25,
                "key": api_key,
            }
            resp = requests.get(YOUTUBE_API_BASE_URL, params=search_params, timeout=15)
            resp.raise_for_status()
            search_data = resp.json()

            video_ids = []
            snippets = {}
            for item in search_data.get("items", []):
                vid_id = item["id"].get("videoId", "")
                if vid_id:
                    video_ids.append(vid_id)
                    snippets[vid_id] = item["snippet"]

            if not video_ids:
                continue

            # Get stats and duration
            stats_params = {
                "part": "statistics,contentDetails,liveStreamingDetails",
                "id": ",".join(video_ids),
                "key": api_key,
            }
            stats_resp = requests.get(
                YOUTUBE_VIDEOS_URL, params=stats_params, timeout=15
            )
            stats_resp.raise_for_status()
            stats_data = stats_resp.json()

            for item in stats_data.get("items", []):
                vid_id = item["id"]
                stats = item.get("statistics", {})
                duration_seconds = _parse_duration(
                    item.get("contentDetails", {}).get("duration", "PT0S")
                )
                is_short = duration_seconds <= 60
                is_livestream = bool(
                    item.get("liveStreamingDetails", {}).get("actualStartTime")
                )
                if is_short:
                    vid_format = "Short"
                elif is_livestream:
                    vid_format = "Livestream"
                else:
                    vid_format = "Long"

                snippet = snippets.get(vid_id, {})
                pub_str = snippet.get("publishedAt", "")
                try:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    is_this_week = pub_dt >= seven_days_ago
                except (ValueError, TypeError):
                    is_this_week = False

                all_videos.append(
                    {
                        "video_id": vid_id,
                        "title": snippet.get("title", ""),
                        "channel": channel_name,
                        "description": snippet.get("description", "")[:300],
                        "published_at": pub_str,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "thumbnail_url": f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                        "view_count": int(stats.get("viewCount", 0)),
                        "like_count": int(stats.get("likeCount", 0)),
                        "comment_count": int(stats.get("commentCount", 0)),
                        "duration_seconds": duration_seconds,
                        "is_short": is_short,
                        "format": vid_format,
                        "period": "week" if is_this_week else "month",
                    }
                )

        except requests.RequestException as e:
            logger.warning(
                "Competitor fetch failed for '%s': %s", channel_name, e
            )

    all_videos.sort(key=lambda v: v["view_count"], reverse=True)
    logger.info("Competitors: found %d videos from %d channels",
                len(all_videos), len(COMPETITOR_CHANNELS))
    return all_videos


def fetch_channel_avatars(api_key: str, channel_ids: list[str]) -> dict[str, str]:
    """Fetch channel avatar URLs for a list of channel IDs.
    Returns dict of channel_id -> avatar_url."""
    avatars = {}
    for batch_start in range(0, len(channel_ids), 50):
        batch = channel_ids[batch_start : batch_start + 50]
        try:
            resp = requests.get(
                YOUTUBE_CHANNELS_URL,
                params={"part": "snippet", "id": ",".join(batch), "key": api_key},
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                thumbnails = item.get("snippet", {}).get("thumbnails", {})
                url = (
                    thumbnails.get("medium")
                    or thumbnails.get("default")
                    or {}
                ).get("url", "")
                if url:
                    avatars[item["id"]] = url
        except requests.RequestException as e:
            logger.warning("Channel avatar fetch failed: %s", e)
    return avatars


def gather_competitor_videos() -> list[dict]:
    """Fetch, tag, and return competitor channel videos."""
    api_key = os.environ.get("YOUTUBE_API_KEY_2", "")
    if not api_key:
        return []
    videos = fetch_competitor_videos(api_key)

    # Fetch channel avatars and attach to each video
    avatar_by_id = fetch_channel_avatars(api_key, list(COMPETITOR_CHANNELS.values()))
    id_to_name = {v: k for k, v in COMPETITOR_CHANNELS.items()}
    avatar_by_name = {id_to_name[cid]: url for cid, url in avatar_by_id.items() if cid in id_to_name}
    for v in videos:
        v["channel_avatar"] = avatar_by_name.get(v["channel"], "")

    # AI-tag competitor videos with JTBD and topic
    cfg = get_llm_config()
    if not cfg["api_key"] or not videos:
        return videos

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    model = cfg["model"]

    batch_size = 25
    for batch_start in range(0, len(videos), batch_size):
        batch = videos[batch_start : batch_start + batch_size]
        video_list = ""
        for i, v in enumerate(batch, 1):
            video_list += (
                f"{i}. \"{v['title']}\" by {v['channel']}\n"
                f"   Description: {(v.get('description') or '')[:150]}\n\n"
            )

        prompt = f"""Tag these YouTube videos. For each, provide:
- "index": video number (1-based)
- "topic": one of: Social Security, Medicare, Investing, Retirement Planning, Tax Strategy, Budgeting, Health & Wellness, Lifestyle, Career, Real Estate, Insurance, General Finance, Other
- "jtbd": array of one or more: "Make Me Feel Better", "Explain a Concept", "Tell Me Where I'm At", "Make a Decision For Me", "Help Me Feel Part of Something", "Make Me Feel Worse"
- "summary": 1 sentence summary

Videos:
{video_list}

Return JSON with "videos" array. ONLY valid JSON."""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(response.choices[0].message.content)
            for item in parsed.get("videos", []):
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    batch[idx]["topic"] = item.get("topic", "Other")
                    batch[idx]["jtbd"] = item.get("jtbd", [])
                    batch[idx]["summary"] = item.get("summary", "")
        except Exception as e:
            logger.error("Competitor tagging failed for batch %d: %s", batch_start, e)

    for v in videos:
        v.setdefault("topic", "Other")
        v.setdefault("jtbd", [])
        v.setdefault("summary", "")

    return videos
