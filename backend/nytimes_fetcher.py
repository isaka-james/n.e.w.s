"""
New York Times API fetcher — https://developer.nytimes.com
Budget: generous (4,000 req/day, 10 req/min) — ~5 calls per generation

Two sub-APIs used:
  Top Stories   : /topstories/v2/{section}.json
  Most Popular  : /mostpopular/v2/viewed/7.json

Sections available: home, arts, automobiles, books/review, business, fashion,
  food, health, home, insider, magazine, movies, nyregion, obituaries, opinion,
  politics, realestate, science, sports, sundayreview, technology, theater,
  t-magazine, travel, upshot, us, world

Strategy:
  S layer : top stories — world section
  S layer : top stories — technology section (global tech)
  S layer : most popular (viral/trending globally)
  S layer : top stories for 1 high-priority tag section
  N layer : article search for user's city (Article Search API)
"""
import hashlib
import logging
from datetime import date, timedelta
import httpx
from config import settings

logger = logging.getLogger(__name__)

NYT_TOP_STORIES     = "https://api.nytimes.com/svc/topstories/v2"
NYT_MOST_POPULAR    = "https://api.nytimes.com/svc/mostpopular/v2"
NYT_ARTICLE_SEARCH  = "https://api.nytimes.com/svc/search/v2/articlesearch.json"

TAG_TO_NYT_SECTION: dict[str, str] = {
    "Technology":    "technology",
    "AI":            "technology",
    "Cybersecurity": "technology",
    "Science":       "science",
    "Space":         "science",
    "Health":        "health",
    "Medicine":      "health",
    "Mental Health": "health",
    "Business":      "business",
    "Finance":       "business",
    "Economy":       "business",
    "Sports":        "sports",
    "Arts":          "arts",
    "Film":          "movies",
    "Books":         "books/review",
    "Food":          "food",
    "Travel":        "travel",
    "Fashion":       "fashion",
    "Politics":      "politics",
    "Climate":       "climate",
    "Environment":   "climate",
    "Real Estate":   "realestate",
    "Automotive":    "automobiles",
}


def _article_id(url: str) -> str:
    return "nyt_" + hashlib.md5(url.encode()).hexdigest()


def _normalize_top_story(item: dict) -> dict | None:
    title = (item.get("title") or "").strip()
    description = (item.get("abstract") or "").strip()
    if not title:
        return None
    url = item.get("url") or ""
    if not url:
        return None

    image_url = None
    # Top Stories API: 'multimedia' is a list of {url, format, subtype, ...} — URLs already absolute
    multimedia = item.get("multimedia")
    if isinstance(multimedia, list) and multimedia:
        first = multimedia[0]
        if isinstance(first, dict):
            image_url = first.get("url") or None

    # Most Popular API: 'media' is a list of {media-metadata: [{url, format}, ...]}
    if not image_url:
        media = item.get("media")
        if isinstance(media, list) and media:
            first_media = media[0]
            if isinstance(first_media, dict):
                meta = first_media.get("media-metadata") or []
                # last entry is the largest size
                if meta and isinstance(meta[-1], dict):
                    image_url = meta[-1].get("url") or None

    section = item.get("section") or item.get("subsection") or ""
    return {
        "article_id": _article_id(url),
        "title": title,
        "description": description,
        "link": url,
        "image_url": image_url,
        "video_url": None,
        "source_name": "The New York Times",
        "source_icon": None,
        "country": None,
        "category": [section] if section else [],
        "keywords": [],
        "pubDate": item.get("published_date") or "",
        "language": "en",
    }


def _normalize_article_search(doc: dict, country: str | None = None) -> dict | None:
    # headline is a dict {"main": "..."} in article search API
    # guard against it being a plain string in case the API varies
    headline_raw = doc.get("headline")
    if isinstance(headline_raw, dict):
        title = (headline_raw.get("main") or "").strip()
    elif isinstance(headline_raw, str):
        title = headline_raw.strip()
    else:
        title = ""

    description = (doc.get("abstract") or doc.get("snippet") or doc.get("lead_paragraph") or "").strip()
    if not title:
        return None
    url = doc.get("web_url") or ""
    if not url:
        return None

    # Article Search API returns multimedia as a DICT: {default: {url, ...}, thumbnail: {url, ...}}
    # Top Stories returns it as a LIST — handle both, URLs are always absolute (no prepend needed)
    image_url = None
    multimedia = doc.get("multimedia")
    if isinstance(multimedia, dict):
        default = multimedia.get("default") or {}
        thumbnail = multimedia.get("thumbnail") or {}
        image_url = (
            (default.get("url") if isinstance(default, dict) else None)
            or (thumbnail.get("url") if isinstance(thumbnail, dict) else None)
        )
    elif isinstance(multimedia, list) and multimedia:
        first = multimedia[0]
        if isinstance(first, dict):
            image_url = first.get("url") or None

    section = doc.get("section_name") or ""
    return {
        "article_id": _article_id(url),
        "title": title,
        "description": description,
        "link": url,
        "image_url": image_url,
        "video_url": None,
        "source_name": "The New York Times",
        "source_icon": None,
        "country": country,
        "category": [section] if section else [],
        "keywords": [],
        "pubDate": doc.get("pub_date") or "",
        "language": "en",
    }


def _fetch_top_stories(section: str) -> list[dict]:
    if not settings.NYTIMES_API_KEY:
        return []
    try:
        resp = httpx.get(
            f"{NYT_TOP_STORIES}/{section}.json",
            params={"api-key": settings.NYTIMES_API_KEY},
            timeout=20,
        )
        data = resp.json()
        items = data.get("results") or []
        out = []
        for item in items:
            n = _normalize_top_story(item)
            if n:
                out.append(n)
        return out
    except Exception as exc:
        logger.warning("NYT top stories failed (section=%s): %s", section, exc)
        return []


def _fetch_most_popular() -> list[dict]:
    if not settings.NYTIMES_API_KEY:
        return []
    try:
        resp = httpx.get(
            f"{NYT_MOST_POPULAR}/viewed/7.json",
            params={"api-key": settings.NYTIMES_API_KEY},
            timeout=20,
        )
        data = resp.json()
        items = data.get("results") or []
        out = []
        for item in items:
            n = _normalize_top_story(item)
            if n:
                out.append(n)
        return out
    except Exception as exc:
        logger.warning("NYT most popular failed: %s", exc)
        return []


def _fetch_article_search(q: str, page_size: int = 10, country: str | None = None) -> list[dict]:
    if not settings.NYTIMES_API_KEY:
        return []
    cutoff = (date.today() - timedelta(days=2)).strftime("%Y%m%d")
    try:
        resp = httpx.get(
            NYT_ARTICLE_SEARCH,
            params={
                "api-key": settings.NYTIMES_API_KEY,
                "q": q,
                "sort": "newest",
                "begin_date": cutoff,
                "fl": "headline,abstract,lead_paragraph,web_url,pub_date,section_name,multimedia",
            },
            timeout=20,
        )
        data = resp.json()
        docs = (data.get("response") or {}).get("docs") or []
        out = []
        for doc in docs[:page_size]:
            n = _normalize_article_search(doc, country=country)
            if n:
                out.append(n)
        return out
    except Exception as exc:
        logger.warning("NYT article search failed (q=%s): %s", q, exc)
        return []


def fetch_nytimes_stories(user) -> list[dict]:
    """
    Fetch from New York Times. Budget: ~15 calls per generation (4,000 req/day).

    Allocation:
      1 call  — S: world top stories (global)
      1 call  — S: technology top stories
      1 call  — S: science top stories
      1 call  — S: health top stories
      1 call  — S: business top stories
      1 call  — S: politics top stories
      1 call  — S: us section (US national, relevant for country E layer)
      1 call  — S: most popular (viral/trending)
      1 call  — N: article search for user's city
      1 call  — E: article search for user's country
      1 call  — W: article search for user's continent keyword
      up to 4 — S: high+medium priority tag sections (deduped)
    """
    if not settings.NYTIMES_API_KEY:
        return []

    all_raw: list[dict] = []
    used_sections: set[str] = set()

    # --- S layer: core always-on sections ---
    core_sections = ["world", "technology", "science", "health", "business", "politics"]
    for section in core_sections:
        all_raw += _fetch_top_stories(section)
        used_sections.add(section)

    # --- E layer: US national section (strong for US-based users, good baseline otherwise) ---
    all_raw += _fetch_top_stories("us")
    used_sections.add("us")

    # --- S layer: most popular (viral / widely-read) ---
    all_raw += _fetch_most_popular()

    # --- N layer: city-specific article search ---
    if user.city:
        all_raw += _fetch_article_search(user.city, page_size=10, country=user.country)

    # --- E layer: country article search ---
    if user.country:
        all_raw += _fetch_article_search(user.country, page_size=10, country=user.country)

    # --- W layer: continent keyword search ---
    continent_keywords: dict[str, str] = {
        "Africa": "Africa",
        "Asia": "Asia",
        "Europe": "Europe",
        "North America": "Latin America OR Caribbean",
        "South America": "South America",
        "Latin America": "Latin America",
        "Oceania": "Pacific OR Australia",
        "Middle East": "Middle East",
    }
    cont_kw = continent_keywords.get(user.continent)
    if cont_kw:
        all_raw += _fetch_article_search(cont_kw, page_size=10)

    # --- S layer: up to 4 tag sections (high priority first, then medium) ---
    all_tags = (
        [t for t in (user.tags or []) if t.get("priority") == "high"] +
        [t for t in (user.tags or []) if t.get("priority") == "medium"]
    )
    tag_calls = 0
    for tag in all_tags:
        if tag_calls >= 4:
            break
        name = tag.get("name", "")
        section = TAG_TO_NYT_SECTION.get(name)
        if section and section not in used_sections:
            all_raw += _fetch_top_stories(section)
            used_sections.add(section)
            tag_calls += 1
        elif not section:
            all_raw += _fetch_article_search(name, page_size=10)
            tag_calls += 1

    return all_raw
