import hashlib
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

NEWSAPI_HEADLINES = "https://newsapi.org/v2/top-headlines"
NEWSAPI_EVERYTHING = "https://newsapi.org/v2/everything"

# NewsAPI only supports a fixed set of categories
TAG_TO_CATEGORY: dict[str, str] = {
    "Technology": "technology",
    "Business": "business",
    "Finance": "business",
    "Health": "health",
    "Science": "science",
    "Sports": "sports",
    "Entertainment": "entertainment",
    "Culture": "entertainment",
}

# Countries that NewsAPI top-headlines supports (subset; others fall back to /everything)
NEWSAPI_COUNTRY_CODES = {
    "Argentina": "ar", "Australia": "au", "Austria": "at", "Belgium": "be",
    "Brazil": "br", "Bulgaria": "bg", "Canada": "ca", "China": "cn",
    "Colombia": "co", "Cuba": "cu", "Czech Republic": "cz", "Egypt": "eg",
    "France": "fr", "Germany": "de", "Greece": "gr", "Hong Kong": "hk",
    "Hungary": "hu", "India": "in", "Indonesia": "id", "Ireland": "ie",
    "Israel": "il", "Italy": "it", "Japan": "jp", "Latvia": "lv",
    "Lithuania": "lt", "Malaysia": "my", "Mexico": "mx", "Morocco": "ma",
    "Netherlands": "nl", "New Zealand": "nz", "Nigeria": "ng", "Norway": "no",
    "Philippines": "ph", "Poland": "pl", "Portugal": "pt", "Romania": "ro",
    "Russia": "ru", "Saudi Arabia": "sa", "Serbia": "rs", "Singapore": "sg",
    "Slovakia": "sk", "Slovenia": "si", "South Africa": "za", "South Korea": "kr",
    "Sweden": "se", "Switzerland": "ch", "Taiwan": "tw", "Thailand": "th",
    "Turkey": "tr", "Ukraine": "ua", "United Arab Emirates": "ae",
    "United Kingdom": "gb", "United States": "us", "Venezuela": "ve",
}


def _article_id(url: str) -> str:
    return "na_" + hashlib.md5(url.encode()).hexdigest()


def _normalize(article: dict, country: str | None = None, category: str | None = None) -> dict | None:
    """Convert a NewsAPI article to the same cleaned format used by the newsdata fetcher."""
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()

    # Drop removed/deleted articles
    if title in ("[Removed]", "") and not description:
        return None
    if not title and not description:
        return None

    url = article.get("url") or ""
    if not url:
        return None

    source = article.get("source") or {}
    source_name = source.get("name") or ""

    # NewsAPI doesn't provide source icons — leave null
    pub = article.get("publishedAt") or ""

    return {
        "article_id": _article_id(url),
        "title": title,
        "description": description,
        "link": url,
        "image_url": article.get("urlToImage"),
        "video_url": None,
        "source_name": source_name,
        "source_icon": None,
        "country": country,
        "category": [category] if category else [],
        "keywords": [],
        "pubDate": pub,
        "language": "en",
    }


def _get(endpoint: str, params: dict) -> list[dict]:
    call_params = {**params, "apiKey": settings.NEWSAPI_API_KEY, "pageSize": 20}
    log_params = {k: v for k, v in call_params.items() if k != "apiKey"}
    try:
        resp = httpx.get(endpoint, params=call_params, timeout=20)
        data = resp.json()
        if data.get("status") == "error":
            logger.warning("NewsAPI error for %s: %s", log_params, data.get("message"))
            return []
        return data.get("articles") or []
    except Exception as exc:
        logger.warning("NewsAPI request failed for %s: %s", log_params, exc)
        return []


def fetch_newsapi_stories(user) -> list[dict]:
    """
    Fetch stories from NewsAPI.org to supplement NewsData.io.
    Stays within 100 req/day: 1 country + 1 city + up to 3 tag calls = max 5 calls.
    """
    country_code = NEWSAPI_COUNTRY_CODES.get(user.country)
    all_raw: list[dict] = []

    # E layer: top headlines for the user's country
    if country_code:
        raw = _get(NEWSAPI_HEADLINES, {"country": country_code, "language": "en"})
        for a in raw:
            n = _normalize(a, country=user.country, category="general")
            if n:
                all_raw.append(n)

    # N layer: everything mentioning the user's city
    city_raw = _get(NEWSAPI_EVERYTHING, {
        "q": f'"{user.city}"',
        "searchIn": "title,description",
        "language": "en",
        "sortBy": "publishedAt",
    })
    for a in city_raw:
        n = _normalize(a, country=user.country, category="general")
        if n:
            all_raw.append(n)

    # S/tag layer: up to 3 high-priority tags
    high_tags = [t for t in user.tags if t.get("priority") == "high"][:3]
    for tag in high_tags:
        tag_name = tag.get("name", "")
        category = TAG_TO_CATEGORY.get(tag_name)

        if category:
            # Use top-headlines with category for well-known topics
            raw = _get(NEWSAPI_HEADLINES, {"category": category, "language": "en"})
            for a in raw:
                n = _normalize(a, country=None, category=category)
                if n:
                    all_raw.append(n)
        else:
            # Fall back to /everything keyword search for niche tags
            raw = _get(NEWSAPI_EVERYTHING, {
                "q": tag_name,
                "language": "en",
                "sortBy": "publishedAt",
                "searchIn": "title,description",
            })
            for a in raw:
                n = _normalize(a, country=None, category=tag_name.lower())
                if n:
                    all_raw.append(n)

    return all_raw
