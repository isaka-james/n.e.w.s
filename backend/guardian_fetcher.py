"""
The Guardian API fetcher — https://open-platform.theguardian.com/documentation/
Budget: 5,000 req/day — use generously (~8–10 calls per report generation)

API endpoint: https://content.guardianapis.com/search
Key fields via show-fields: headline, trailText, thumbnail, byline

Strategy:
  N layer : search by city keyword        (most-recent ordering)
  E layer : search by country keyword     (most-recent ordering)
  W layer : climate + environment section (continent-level themes)
  S layer : world section                 (global)
  S layer : technology section            (tech = always global)
  S layer : science section
  S layer : up to 3 high-priority tag searches
"""
import hashlib
import logging
import threading
import time
from datetime import date, timedelta
import httpx
from config import settings

logger = logging.getLogger(__name__)

GUARDIAN_BASE = "https://content.guardianapis.com"

# Rate limit: 1 req/s (strict Guardian cap). Keep 100 ms safety margin.
_throttle_lock = threading.Lock()
_throttle_last_call_at = 0.0
_THROTTLE_MIN_INTERVAL = 1.1  # seconds


def _throttle() -> None:
    """Block until at least _THROTTLE_MIN_INTERVAL has elapsed since the last Guardian call."""
    global _throttle_last_call_at
    with _throttle_lock:
        delta = time.monotonic() - _throttle_last_call_at
        if delta < _THROTTLE_MIN_INTERVAL:
            time.sleep(_THROTTLE_MIN_INTERVAL - delta)
        _throttle_last_call_at = time.monotonic()

TAG_TO_GUARDIAN_SECTION: dict[str, str] = {
    "Technology":    "technology",
    "AI":            "technology",
    "Cybersecurity": "technology",
    "Gaming":        "technology",
    "Science":       "science",
    "Space":         "science",
    "Environment":   "environment",
    "Climate":       "environment",
    "Energy":        "environment",
    "Business":      "business",
    "Finance":       "business",
    "Economy":       "business",
    "Sports":        "sport",
    "Culture":       "culture",
    "Entertainment": "culture",
    "Music":         "music",
    "Film":          "film",
    "Books":         "books",
    "Education":     "education",
    "Health":        "society",
    "Mental Health": "society",
    "Law":           "law",
    "Politics":      "politics",
    "Geopolitics":   "world",
    "Defense":       "world",
}


def _article_id(url: str) -> str:
    return "gu_" + hashlib.md5(url.encode()).hexdigest()


def _normalize(item: dict, category: str | None = None, country: str | None = None, fetch_target: str | None = None) -> dict | None:
    fields = item.get("fields") or {}
    title = (fields.get("headline") or item.get("webTitle") or "").strip()
    description = (fields.get("trailText") or "").strip()
    if not title:
        return None
    url = item.get("webUrl") or ""
    if not url:
        return None
    pub = item.get("webPublicationDate") or ""
    section = item.get("sectionName") or category or ""
    return {
        "article_id": _article_id(url),
        "title": title,
        "description": description,
        "link": url,
        "image_url": fields.get("thumbnail") or None,
        "video_url": None,
        "source_name": "The Guardian",
        "source_icon": None,
        "country": country,
        "category": [section] if section else [],
        "fetch_target": fetch_target or "global",
        "keywords": [],
        "pubDate": pub,
        "language": "en",
    }


def _search(q: str | None = None, section: str | None = None, page_size: int = 15) -> list[dict]:
    if not settings.GUARDIAN_API_KEY:
        return []
    cutoff = (date.today() - timedelta(days=2)).isoformat()
    params: dict = {
        "api-key": settings.GUARDIAN_API_KEY,
        "show-fields": "headline,trailText,thumbnail",
        "order-by": "newest",
        "page-size": str(page_size),
        "from-date": cutoff,
    }
    if q:
        params["q"] = q
    if section:
        params["section"] = section
    try:
        _throttle()
        resp = httpx.get(f"{GUARDIAN_BASE}/search", params=params, timeout=20)
        data = resp.json()
        results = data.get("response", {}).get("results") or []
        return results
    except Exception as exc:
        logger.warning("Guardian search failed (q=%s section=%s): %s", q, section, exc)
        return []


def fetch_guardian_stories(user) -> list[dict]:
    """
    Fetch from The Guardian. Budget: ~36 calls per generation (5,000 req/day cap).
    Rate limit: 1 req/s — enforced by _throttle() inside _search().
    Note: fetch_local_boost() consumes 3 additional Guardian calls per generation.

    Allocation (intentionally aggressive — Guardian has plenty of headroom):
      3 calls  — N: city exact phrase + city broad + city in headline
      4 calls  — E: country keyword + country politics + country economy + country news
      up to 2  — W: continent keyword + continent politics (conditional on continent map)
      9 calls  — S: core sections (world, tech, science, business, politics, sport,
                                   culture, environment, lifestyle)
      up to 10 — S: high-priority tags: new section call OR keyword search for topics
                    whose section is already covered by a core section (deduped)
      up to 8  — S: medium-priority tag keyword searches
    Max: ~36 calls → 5,000/day safely covers ~138 generations/day.
    """
    if not settings.GUARDIAN_API_KEY:
        return []

    all_raw: list[dict] = []
    seen_sections: set[str] = set()

    def add(items: list[dict], category: str | None = None, country: str | None = None, fetch_target: str | None = None) -> None:
        for item in items:
            n = _normalize(item, category=category, country=country, fetch_target=fetch_target)
            if n:
                all_raw.append(n)

    # --- N layer: city searches (3 angles) ---
    add(_search(q=f'"{user.city}"', page_size=30), category="local", country=user.country, fetch_target="local")
    add(_search(q=user.city, page_size=25), category="local", country=user.country, fetch_target="local")
    add(_search(q=f"{user.city} news", page_size=15), category="local", country=user.country, fetch_target="local")

    # --- E layer: country searches (4 angles) ---
    add(_search(q=user.country, page_size=40), category="national", country=user.country, fetch_target="national")
    add(_search(q=f"{user.country} politics", page_size=20), category="politics", country=user.country, fetch_target="national")
    add(_search(q=f"{user.country} economy", page_size=20), category="business", country=user.country, fetch_target="national")
    add(_search(q=f"{user.country} news", page_size=20), category="national", country=user.country, fetch_target="national")

    # --- W layer: continent + continent politics ---
    continent_kw = {
        "Africa": "Africa", "Asia": "Asia", "Europe": "Europe",
        "North America": "Americas", "South America": "Latin America",
        "Oceania": "Pacific",
    }.get(user.continent, user.continent)
    if continent_kw:
        add(_search(q=continent_kw, page_size=30), category="regional", fetch_target="regional")
        add(_search(q=f"{continent_kw} politics", page_size=20), category="regional", fetch_target="regional")

    # --- S layer: core always-on global sections ---
    core_sections = [
        ("world", "world", 30),
        ("technology", "technology", 25),
        ("science", "science", 25),
        ("business", "business", 25),
        ("politics", "politics", 20),
        ("sport", "sport", 20),
        ("culture", "culture", 20),
        ("environment", "environment", 20),
        ("lifestyle", "lifestyle", 15),
    ]
    for section, category, size in core_sections:
        add(_search(section=section, page_size=size), category=category, fetch_target="global")
        seen_sections.add(section)

    # --- S layer: up to 10 high-priority tags ---
    high_tags = [t for t in (user.tags or []) if t.get("priority") == "high"]
    tag_calls = 0
    section_kw_done: set[str] = set()  # track keyword searches done for section-mapped topics
    for tag in high_tags:
        if tag_calls >= 10:
            break
        name = tag.get("name", "")
        section = TAG_TO_GUARDIAN_SECTION.get(name)
        if section and section not in seen_sections:
            add(_search(section=section, page_size=20), category=section, fetch_target="global")
            seen_sections.add(section)
            tag_calls += 1
        elif section:
            # Section already covered — do a direct keyword search so this
            # topic still gets its own article coverage.
            if name not in section_kw_done:
                add(_search(q=name, page_size=15), category=section, fetch_target="global")
                section_kw_done.add(name)
                tag_calls += 1
        else:
            add(_search(q=name, page_size=20), category=name.lower(), fetch_target="global")
            tag_calls += 1

    # --- S layer: up to 8 medium-priority tags (keyword search) ---
    med_tags = [t for t in (user.tags or []) if t.get("priority") == "medium"]
    med_calls = 0
    for tag in med_tags:
        if med_calls >= 8:
            break
        name = tag.get("name", "")
        add(_search(q=name, page_size=15), category=name.lower(), fetch_target="global")
        med_calls += 1

    return all_raw
