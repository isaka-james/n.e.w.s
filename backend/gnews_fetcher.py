"""
GNews API fetcher — https://gnews.io/api/v4
Rate limits:
  - 100 requests / day (daily cap)
  - 1 request / second (≈10 requests / minute)

Both ceilings apply, so we throttle outgoing calls to ~0.9 req/s in-process
to stay safely under the per-second limit. The daily cap is managed by simply
keeping the per-generation budget at ~10 calls (≤10 gens/day).

Strategy:
  - S layer  : top-headlines for each of the user's high-priority tag categories (global)
  - S layer  : search for the user's custom/low-priority tags that have no category mapping
  - E layer  : top-headlines filtered by country  (country top-news)
  - N layer  : search for the user's city name

GNews categories: general, world, nation, business, technology,
                  entertainment, sports, science, health
"""
import hashlib
import logging
import threading
import time
from datetime import date, timedelta

import httpx
from config import settings

logger = logging.getLogger(__name__)

# Per-process rate limit: GNews allows 1 req/s. Keep a 100ms safety margin.
_throttle_lock = threading.Lock()
_throttle_last_call_at = 0.0
_THROTTLE_MIN_INTERVAL = 1.1  # seconds


def _throttle() -> None:
    """Block until at least _THROTTLE_MIN_INTERVAL has elapsed since the last call."""
    global _throttle_last_call_at
    with _throttle_lock:
        delta = time.monotonic() - _throttle_last_call_at
        if delta < _THROTTLE_MIN_INTERVAL:
            time.sleep(_THROTTLE_MIN_INTERVAL - delta)
        _throttle_last_call_at = time.monotonic()

GNEWS_SEARCH    = "https://gnews.io/api/v4/search"
GNEWS_HEADLINES = "https://gnews.io/api/v4/top-headlines"

TAG_TO_GNEWS_CATEGORY: dict[str, str] = {
    "Technology":    "technology",
    "AI":            "technology",
    "Cybersecurity": "technology",
    "Gaming":        "technology",
    "Business":      "business",
    "Finance":       "business",
    "Economy":       "business",
    "Startup":       "business",
    "Science":       "science",
    "Space":         "science",
    "Medicine":      "health",
    "Health":        "health",
    "Mental Health": "health",
    "Sports":        "sports",
    "Entertainment": "entertainment",
    "Music":         "entertainment",
    "Film":          "entertainment",
    "Fashion":       "entertainment",
    "Culture":       "entertainment",
    "Politics":      "nation",
    "Law":           "nation",
    "Geopolitics":   "world",
    "Defense":       "world",
    "Climate":       "world",
    "Energy":        "world",
    "Environment":   "world",
}

# Country name → GNews-compatible 2-letter ISO code (lowercase)
GNEWS_COUNTRY_CODES: dict[str, str] = {
    "Argentina": "ar", "Australia": "au", "Austria": "at", "Belgium": "be",
    "Brazil": "br", "Canada": "ca", "China": "cn", "Czech Republic": "cz",
    "Egypt": "eg", "France": "fr", "Germany": "de", "Greece": "gr",
    "Hungary": "hu", "India": "in", "Indonesia": "id", "Ireland": "ie",
    "Israel": "il", "Italy": "it", "Japan": "jp", "Kenya": "ke",
    "Mexico": "mx", "Netherlands": "nl", "New Zealand": "nz", "Nigeria": "ng",
    "Norway": "no", "Philippines": "ph", "Poland": "pl", "Portugal": "pt",
    "Romania": "ro", "Russia": "ru", "Saudi Arabia": "sa", "Singapore": "sg",
    "South Africa": "za", "South Korea": "kr", "Spain": "es", "Sweden": "se",
    "Switzerland": "ch", "Taiwan": "tw", "Thailand": "th", "Turkey": "tr",
    "Ukraine": "ua", "United Arab Emirates": "ae", "United Kingdom": "gb",
    "United States": "us",
}


def _article_id(url: str) -> str:
    return "gn_" + hashlib.md5(url.encode()).hexdigest()


def _normalize(article: dict, country: str | None = None, category: str | None = None) -> dict | None:
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    if not title and not description:
        return None
    url = article.get("url") or ""
    if not url:
        return None
    source = article.get("source") or {}
    source_name = source.get("name") or source.get("url") or ""
    pub = article.get("publishedAt") or ""
    return {
        "article_id": _article_id(url),
        "title": title,
        "description": description,
        "link": url,
        "image_url": article.get("image") or None,
        "video_url": None,
        "source_name": source_name,
        "source_icon": None,
        "country": country,
        "category": [category] if category else [],
        "keywords": [],
        "pubDate": pub,
        "language": "en",
    }


def _search(params: dict) -> list[dict]:
    if not settings.GNEWS_API_KEY:
        return []
    cutoff = (date.today() - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
    call_params = {**params, "apikey": settings.GNEWS_API_KEY, "lang": "en", "max": 10, "from": cutoff}
    try:
        _throttle()
        resp = httpx.get(GNEWS_SEARCH, params=call_params, timeout=20)
        data = resp.json()
        if "errors" in data:
            logger.warning("GNews search error %s: %s", params, data["errors"])
            return []
        return data.get("articles") or []
    except Exception as exc:
        logger.warning("GNews search failed %s: %s", params, exc)
        return []


def _headlines(params: dict) -> list[dict]:
    if not settings.GNEWS_API_KEY:
        return []
    call_params = {**params, "apikey": settings.GNEWS_API_KEY, "lang": "en", "max": 10}
    try:
        _throttle()
        resp = httpx.get(GNEWS_HEADLINES, params=call_params, timeout=20)
        data = resp.json()
        if "errors" in data:
            logger.warning("GNews headlines error %s: %s", params, data["errors"])
            return []
        return data.get("articles") or []
    except Exception as exc:
        logger.warning("GNews headlines failed %s: %s", params, exc)
        return []


def fetch_gnews_stories(user) -> list[dict]:
    """
    Fetch from GNews. Budget: ~10 calls per generation (100 req/day → ~10 gens/day).

    Allocation:
      2 calls  — E: country general + country nation headlines
      2 calls  — N: city exact phrase + city broad search
      1 call   — S: world top-headlines (global trending)
      1 call   — S: general top-headlines (catch-all)
      up to 4  — S: categories from high-priority tags (deduped)
    """
    if not settings.GNEWS_API_KEY:
        return []

    all_raw: list[dict] = []
    used_categories: set[str] = set()

    # E layer: country top-headlines (general)
    country_code = GNEWS_COUNTRY_CODES.get(user.country)
    if country_code:
        raw = _headlines({"country": country_code, "category": "general"})
        for a in raw:
            n = _normalize(a, country=user.country, category="general")
            if n:
                all_raw.append(n)

        # E layer: national headlines (politics/policy from the user's country)
        raw = _headlines({"country": country_code, "category": "nation"})
        for a in raw:
            n = _normalize(a, country=user.country, category="nation")
            if n:
                all_raw.append(n)
        used_categories.add("nation")

    # N layer: city exact phrase search
    city_raw = _search({"q": f'"{user.city}"'})
    for a in city_raw:
        n = _normalize(a, country=user.country, category="local")
        if n:
            all_raw.append(n)

    # N layer: city broader search (captures "city region" variants)
    city_broad = _search({"q": user.city, "in": "title"})
    for a in city_broad:
        n = _normalize(a, country=user.country, category="local")
        if n:
            all_raw.append(n)

    # S layer: world top-headlines
    world_raw = _headlines({"category": "world"})
    for a in world_raw:
        n = _normalize(a, country=None, category="world")
        if n:
            all_raw.append(n)
    used_categories.add("world")

    # S layer: general top-headlines (globally trending)
    gen_raw = _headlines({"category": "general"})
    for a in gen_raw:
        n = _normalize(a, country=None, category="general")
        if n:
            all_raw.append(n)
    used_categories.add("general")

    # S layer: up to 4 tag categories (high priority first, then medium)
    all_tags = (
        [t for t in (user.tags or []) if t.get("priority") == "high"] +
        [t for t in (user.tags or []) if t.get("priority") == "medium"]
    )
    extra_calls = 0
    for tag in all_tags:
        if extra_calls >= 4:
            break
        tag_name = tag.get("name", "")
        cat = TAG_TO_GNEWS_CATEGORY.get(tag_name)
        if cat and cat not in used_categories:
            raw = _headlines({"category": cat})
            for a in raw:
                n = _normalize(a, country=None, category=cat)
                if n:
                    all_raw.append(n)
            used_categories.add(cat)
            extra_calls += 1
        elif not cat:
            # Keyword search for niche tags without a GNews category mapping
            raw = _search({"q": tag_name, "in": "title,description"})
            for a in raw:
                n = _normalize(a, country=None, category=tag_name.lower())
                if n:
                    all_raw.append(n)
            extra_calls += 1

    return all_raw
