import hashlib
import logging
from datetime import date, timedelta
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


def _normalize(article: dict, country: str | None = None, category: str | None = None, fetch_target: str | None = None) -> dict | None:
    """Convert a NewsAPI article to the same cleaned format used by the newsdata fetcher."""
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()

    # Drop deleted/removed articles regardless of description
    if title == "[Removed]":
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
        "fetch_target": fetch_target or "global",
        "keywords": [],
        "pubDate": pub,
        "language": "en",
    }


def _get(endpoint: str, params: dict) -> list[dict]:
    call_params = {**params, "apiKey": settings.NEWSAPI_API_KEY, "pageSize": 100}
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


# Continent keyword map for broad W-layer coverage
CONTINENT_KEYWORDS: dict[str, str] = {
    "Africa": "Africa",
    "Asia": "Asia",
    "Europe": "Europe",
    "North America": "Americas",
    "South America": "Americas",
    "Latin America": "Latin America",
    "Oceania": "Pacific",
    "Middle East": "Middle East",
}

# All NewsAPI categories — used for broad country coverage
ALL_CATEGORIES = ["general", "business", "entertainment", "health", "science", "sports", "technology"]


def fetch_newsapi_stories(user) -> list[dict]:
    """
    Fetch stories from NewsAPI.org.
    Budget: ~18 calls per generation (100 req/day → ~5 generations/day).

    Allocation:
      up to 2  — E: country general + business top-headlines (conditional on country code)
      2 calls  — N: city exact phrase + city broad keyword search
      up to 2  — W: continent keyword + "<continent> news" (conditional on continent map)
      up to 3  — S: country technology/health/science cross-section (conditional on country code)
      up to 5  — S: high-priority tag categories or keyword searches
      up to 4  — S: medium-priority tag keyword searches
    Max: ~18 calls → 100/day safely covers ~5 generations/day.
    """
    country_code = NEWSAPI_COUNTRY_CODES.get(user.country)
    all_raw: list[dict] = []
    used_categories: set[str] = set()
    from_date = (date.today() - timedelta(days=2)).isoformat()

    # --- E layer: country top-headlines (general) ---
    if country_code:
        for cat in ("general", "business"):
            raw = _get(NEWSAPI_HEADLINES, {"country": country_code, "category": cat})
            for a in raw:
                n = _normalize(a, country=user.country, category=cat, fetch_target="national")
                if n:
                    all_raw.append(n)
            used_categories.add(cat)

    # --- N layer: city exact phrase, sorted by freshness ---
    city_raw = _get(NEWSAPI_EVERYTHING, {
        "q": f'"{user.city}"',
        "searchIn": "title,description",
        "language": "en",
        "sortBy": "publishedAt",
        "from": from_date,
    })
    for a in city_raw:
        n = _normalize(a, country=user.country, category="local", fetch_target="local")
        if n:
            all_raw.append(n)

    # --- N layer: city broad search, sorted by relevance (catches more) ---
    city_rel = _get(NEWSAPI_EVERYTHING, {
        "q": user.city,
        "language": "en",
        "sortBy": "relevancy",
        "from": from_date,
    })
    for a in city_rel:
        n = _normalize(a, country=user.country, category="local", fetch_target="local")
        if n:
            all_raw.append(n)

    # --- W layer: continent keyword search ---
    continent_kw = CONTINENT_KEYWORDS.get(user.continent)
    if continent_kw:
        cont_raw = _get(NEWSAPI_EVERYTHING, {
            "q": continent_kw,
            "language": "en",
            "sortBy": "publishedAt",
            "from": from_date,
        })
        for a in cont_raw:
            n = _normalize(a, country=None, category="world", fetch_target="regional")
            if n:
                all_raw.append(n)
        # Second W call: "<continent> news" for broader coverage
        cont_news = _get(NEWSAPI_EVERYTHING, {
            "q": f"{continent_kw} news",
            "language": "en",
            "sortBy": "relevancy",
            "from": from_date,
        })
        for a in cont_news:
            n = _normalize(a, country=None, category="world", fetch_target="regional")
            if n:
                all_raw.append(n)

    # --- S layer: country + each available category (tech, health, science…) ---
    if country_code:
        for cat in ("technology", "health", "science"):
            if cat not in used_categories:
                raw = _get(NEWSAPI_HEADLINES, {"country": country_code, "category": cat})
                for a in raw:
                    n = _normalize(a, country=user.country, category=cat, fetch_target="national")
                    if n:
                        all_raw.append(n)
                used_categories.add(cat)

    # --- S layer: high-priority tags (up to 5 calls) ---
    high_tags = [t for t in (user.tags or []) if t.get("priority") == "high"][:5]
    for tag in high_tags:
        tag_name = tag.get("name", "")
        category = TAG_TO_CATEGORY.get(tag_name)
        if category and category not in used_categories:
            raw = _get(NEWSAPI_HEADLINES, {"category": category, "language": "en"})
            for a in raw:
                n = _normalize(a, country=None, category=category, fetch_target="global")
                if n:
                    all_raw.append(n)
            used_categories.add(category)
        elif not category:
            raw = _get(NEWSAPI_EVERYTHING, {
                "q": tag_name,
                "language": "en",
                "sortBy": "publishedAt",
                "searchIn": "title,description",
                "from": from_date,
            })
            for a in raw:
                n = _normalize(a, country=None, category=tag_name.lower(), fetch_target="global")
                if n:
                    all_raw.append(n)

    # --- S layer: medium-priority tags (up to 4 calls, keyword only) ---
    med_tags = [t for t in (user.tags or []) if t.get("priority") == "medium"][:4]
    for tag in med_tags:
        tag_name = tag.get("name", "")
        raw = _get(NEWSAPI_EVERYTHING, {
            "q": tag_name,
            "language": "en",
            "sortBy": "publishedAt",
            "from": from_date,
        })
        for a in raw:
            n = _normalize(a, country=None, category=tag_name.lower(), fetch_target="global")
            if n:
                all_raw.append(n)

    return all_raw
