"""
Configuration for the Retirement Daily Digest.
Customize topics, search queries, and sources here.
"""

# Each topic has a display name and a list of search queries used to find articles.
# The tool searches across NewsAPI and RSS feeds for each query.
TOPICS = {
    "social_security": {
        "name": "Social Security & Medicare",
        "queries": [
            '"social security" benefits',
            '"social security" COLA',
            '"medicare" coverage OR premiums',
            '"social security" reform OR cuts',
        ],
        "rss_feeds": [
            "https://www.ssa.gov/news/rss/press.xml",
        ],
    },
    "personal_finance": {
        "name": "Personal Finance & Retirement Planning",
        "queries": [
            '"retirement savings" OR "retirement planning"',
            '"401k" OR "IRA" OR "Roth" retirement',
            '"pension" retirees OR retirement',
            '"required minimum distribution" OR "RMD"',
        ],
        "rss_feeds": [],
    },
    "investing": {
        "name": "Investing & Markets",
        "queries": [
            '"retirement" investing OR portfolio',
            '"dividend" stocks retirees OR seniors',
            '"bond" market retirement OR retirees',
            'index fund OR ETF retirement',
        ],
        "rss_feeds": [],
    },
    "legislation": {
        "name": "Legislation & Government Action",
        "queries": [
            "retirement legislation congress",
            "senior citizens government policy",
            "elder care legislation",
            "retirement age policy",
            "SECURE Act retirement",
        ],
        "rss_feeds": [],
    },
    "health_fitness": {
        "name": "Health & Fitness for 60+",
        "queries": [
            "senior fitness exercise study",
            "health tips over 60",
            "aging health research",
            "longevity science news",
        ],
        "rss_feeds": [],
    },
    "job_security": {
        "name": "Job Security & Encore Careers",
        "queries": [
            "older workers job market",
            "age discrimination employment",
            "encore career retirement",
            "working after retirement",
        ],
        "rss_feeds": [],
    },
    "intergenerational": {
        "name": "Inter-generational Relationships",
        "queries": [
            "grandparents grandchildren relationship",
            "baby boomers millennials gen-z",
            "intergenerational wealth transfer",
            "sandwich generation caregiving",
        ],
        "rss_feeds": [],
    },
    "notable_quotes": {
        "name": "What Prominent People Are Saying",
        "queries": [
            '"retirement" advice expert OR advisor',
            '"social security" statement OR comment senator OR congressman',
            'retirement workforce CEO OR executive',
        ],
        "rss_feeds": [],
    },
}

# Maximum number of articles to include per topic
MAX_ARTICLES_PER_TOPIC = 5

# Maximum total articles across all topics
MAX_TOTAL_ARTICLES = 30

# NewsAPI settings
NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"
NEWSAPI_LANGUAGE = "en"
NEWSAPI_SORT_BY = "publishedAt"
NEWSAPI_PAGE_SIZE = 5

# --- LLM Provider ---
# Set LLM_PROVIDER in .env to "groq" or "openai"
# Defaults to groq. Falls back gracefully if one provider's key is missing.
import os as _os

LLM_PROVIDER = _os.environ.get("LLM_PROVIDER", "groq").lower()

# Groq (free tier)
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# OpenAI
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_BASE_URL = "https://api.openai.com/v1"


def get_llm_config() -> dict:
    """Return the active LLM provider config: api_key, base_url, model."""
    provider = LLM_PROVIDER

    # Try preferred provider first, fall back to the other
    if provider == "openai":
        key = _os.environ.get("OPENAI_API_KEY", "")
        if key:
            return {"api_key": key, "base_url": OPENAI_BASE_URL, "model": OPENAI_MODEL}
        # Fall back to groq
        key = _os.environ.get("GROQ_API_KEY", "")
        if key:
            return {"api_key": key, "base_url": GROQ_BASE_URL, "model": GROQ_MODEL}
    else:
        key = _os.environ.get("GROQ_API_KEY", "")
        if key:
            return {"api_key": key, "base_url": GROQ_BASE_URL, "model": GROQ_MODEL}
        # Fall back to openai
        key = _os.environ.get("OPENAI_API_KEY", "")
        if key:
            return {"api_key": key, "base_url": OPENAI_BASE_URL, "model": OPENAI_MODEL}

    return {"api_key": "", "base_url": "", "model": ""}

# Email subject line template (date will be inserted)
EMAIL_SUBJECT_TEMPLATE = "🌅 Retirement Daily Digest — {date}"

# Output file (HTML digest is also saved locally)
OUTPUT_DIR = "output"

# YouTube Data API settings
# Get a free API key at https://console.cloud.google.com/apis/credentials
# Enable "YouTube Data API v3" in your project
YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_SEARCH_QUERIES = [
    "social security retirement 2026",
    "retirement planning tips",
    "retirement investing income",
    "Medicare tips seniors",
    "retire early financial independence",
    "social security COLA",
    "retirement budget fixed income",
]
YOUTUBE_DAYS_BACK = 7
YOUTUBE_MAX_RESULTS_PER_QUERY = 25
YOUTUBE_MIN_VIEW_COUNT = 1000  # Only include videos with this many views
