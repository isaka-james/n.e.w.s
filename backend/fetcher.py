import logging
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from config import settings

logger = logging.getLogger(__name__)

NEWSDATA_BASE = "https://newsdata.io/api/1/latest"

PAID_PLACEHOLDER = "ONLY AVAILABLE IN PAID PLANS"

CONTINENT_KEYWORDS = {
    "Africa": "Africa",
    "Asia": "Asia",
    "Europe": "Europe",
    "North America": "Americas",
    "South America": "LatAm",
    "Oceania": "Pacific",
}

# Reverse map: ISO code → full country name (for enriching articles before DeepSeek)
CODE_TO_COUNTRY = {v: k for k, v in {
    "Afghanistan": "af", "Albania": "al", "Algeria": "dz", "Argentina": "ar",
    "Armenia": "am", "Australia": "au", "Austria": "at", "Azerbaijan": "az",
    "Bahrain": "bh", "Bangladesh": "bd", "Belarus": "by", "Belgium": "be",
    "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Botswana": "bw",
    "Brazil": "br", "Brunei": "bn", "Bulgaria": "bg", "Cambodia": "kh",
    "Cameroon": "cm", "Canada": "ca", "Chile": "cl", "China": "cn",
    "Colombia": "co", "Costa Rica": "cr", "Croatia": "hr", "Cuba": "cu",
    "Cyprus": "cy", "Czech Republic": "cz", "Denmark": "dk", "Dominican Republic": "do",
    "Ecuador": "ec", "Egypt": "eg", "Estonia": "ee", "Ethiopia": "et",
    "Finland": "fi", "France": "fr", "Gabon": "ga", "Georgia": "ge",
    "Germany": "de", "Ghana": "gh", "Greece": "gr", "Guatemala": "gt",
    "Honduras": "hn", "Hungary": "hu", "Iceland": "is", "India": "in",
    "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Ireland": "ie",
    "Israel": "il", "Italy": "it", "Jamaica": "jm", "Japan": "jp",
    "Jordan": "jo", "Kazakhstan": "kz", "Kenya": "ke", "Kuwait": "kw",
    "Kyrgyzstan": "kg", "Laos": "la", "Latvia": "lv", "Lebanon": "lb",
    "Liberia": "lr", "Libya": "ly", "Lithuania": "lt", "Luxembourg": "lu",
    "Madagascar": "mg", "Malaysia": "my", "Maldives": "mv", "Mali": "ml",
    "Malta": "mt", "Mauritius": "mu", "Mexico": "mx", "Moldova": "md",
    "Mongolia": "mn", "Montenegro": "me", "Morocco": "ma", "Mozambique": "mz",
    "Myanmar": "mm", "Namibia": "na", "Nepal": "np", "Netherlands": "nl",
    "New Zealand": "nz", "Nicaragua": "ni", "Niger": "ne", "Nigeria": "ng",
    "North Korea": "kp", "North Macedonia": "mk", "Norway": "no", "Oman": "om",
    "Pakistan": "pk", "Panama": "pa", "Paraguay": "py", "Peru": "pe",
    "Philippines": "ph", "Poland": "pl", "Portugal": "pt", "Qatar": "qa",
    "Romania": "ro", "Russia": "ru", "Rwanda": "rw", "Saudi Arabia": "sa",
    "Senegal": "sn", "Serbia": "rs", "Singapore": "sg", "Slovakia": "sk",
    "Slovenia": "si", "Somalia": "so", "South Africa": "za", "South Korea": "kr",
    "South Sudan": "ss", "Spain": "es", "Sri Lanka": "lk", "Sudan": "sd",
    "Sweden": "se", "Switzerland": "ch", "Syria": "sy", "Taiwan": "tw",
    "Tajikistan": "tj", "Tanzania": "tz", "Thailand": "th", "Tunisia": "tn",
    "Turkey": "tr", "Turkmenistan": "tm", "Uganda": "ug", "Ukraine": "ua",
    "United Arab Emirates": "ae", "United Kingdom": "gb", "United States": "us",
    "Uruguay": "uy", "Uzbekistan": "uz", "Venezuela": "ve", "Vietnam": "vn",
    "Yemen": "ye", "Zambia": "zm", "Zimbabwe": "zw",
}.items()}

COUNTRY_CODE_MAP = {
    "Afghanistan": "af", "Albania": "al", "Algeria": "dz", "Argentina": "ar",
    "Armenia": "am", "Australia": "au", "Austria": "at", "Azerbaijan": "az",
    "Bahrain": "bh", "Bangladesh": "bd", "Belarus": "by", "Belgium": "be",
    "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Botswana": "bw",
    "Brazil": "br", "Brunei": "bn", "Bulgaria": "bg", "Cambodia": "kh",
    "Cameroon": "cm", "Canada": "ca", "Chile": "cl", "China": "cn",
    "Colombia": "co", "Costa Rica": "cr", "Croatia": "hr", "Cuba": "cu",
    "Cyprus": "cy", "Czech Republic": "cz", "Denmark": "dk", "Dominican Republic": "do",
    "Ecuador": "ec", "Egypt": "eg", "Estonia": "ee", "Ethiopia": "et",
    "Finland": "fi", "France": "fr", "Gabon": "ga", "Georgia": "ge",
    "Germany": "de", "Ghana": "gh", "Greece": "gr", "Guatemala": "gt",
    "Honduras": "hn", "Hungary": "hu", "Iceland": "is", "India": "in",
    "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Ireland": "ie",
    "Israel": "il", "Italy": "it", "Jamaica": "jm", "Japan": "jp",
    "Jordan": "jo", "Kazakhstan": "kz", "Kenya": "ke", "Kuwait": "kw",
    "Kyrgyzstan": "kg", "Laos": "la", "Latvia": "lv", "Lebanon": "lb",
    "Liberia": "lr", "Libya": "ly", "Lithuania": "lt", "Luxembourg": "lu",
    "Madagascar": "mg", "Malaysia": "my", "Maldives": "mv", "Mali": "ml",
    "Malta": "mt", "Mauritius": "mu", "Mexico": "mx", "Moldova": "md",
    "Mongolia": "mn", "Montenegro": "me", "Morocco": "ma", "Mozambique": "mz",
    "Myanmar": "mm", "Namibia": "na", "Nepal": "np", "Netherlands": "nl",
    "New Zealand": "nz", "Nicaragua": "ni", "Niger": "ne", "Nigeria": "ng",
    "North Korea": "kp", "North Macedonia": "mk", "Norway": "no", "Oman": "om",
    "Pakistan": "pk", "Panama": "pa", "Paraguay": "py", "Peru": "pe",
    "Philippines": "ph", "Poland": "pl", "Portugal": "pt", "Qatar": "qa",
    "Romania": "ro", "Russia": "ru", "Rwanda": "rw", "Saudi Arabia": "sa",
    "Senegal": "sn", "Serbia": "rs", "Singapore": "sg", "Slovakia": "sk",
    "Slovenia": "si", "Somalia": "so", "South Africa": "za", "South Korea": "kr",
    "South Sudan": "ss", "Spain": "es", "Sri Lanka": "lk", "Sudan": "sd",
    "Sweden": "se", "Switzerland": "ch", "Syria": "sy", "Taiwan": "tw",
    "Tajikistan": "tj", "Tanzania": "tz", "Thailand": "th", "Tunisia": "tn",
    "Turkey": "tr", "Turkmenistan": "tm", "Uganda": "ug", "Ukraine": "ua",
    "United Arab Emirates": "ae", "United Kingdom": "gb", "United States": "us",
    "Uruguay": "uy", "Uzbekistan": "uz", "Venezuela": "ve", "Vietnam": "vn",
    "Yemen": "ye", "Zambia": "zm", "Zimbabwe": "zw",
}


def _is_within_3_days(pub_date_str: str) -> bool:
    """Return True if pub_date_str falls on today, yesterday, or the day before.

    Articles with an unparseable or missing date are kept (lenient fallback).
    """
    if not pub_date_str:
        return True
    today = date.today()
    cutoff = today - timedelta(days=2)
    try:
        # Normalise both "2024-05-12 14:00:00" and ISO 8601 "2024-05-12T14:00:00Z"
        normalized = pub_date_str.strip().replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        pub_day = datetime.fromisoformat(normalized).date()
    except (ValueError, TypeError):
        return True
    return pub_day >= cutoff


def _clean_article(article: dict) -> dict | None:
    """Return a cleaned article dict with only fields useful for DeepSeek, or None to drop it."""
    # Drop press releases
    if article.get("datatype") == "pressrelease":
        return None

    # Drop duplicates flagged by NewsData
    if article.get("duplicate") is True:
        return None

    title = article.get("title") or ""
    description = article.get("description") or ""

    # Drop if both are empty or just placeholders
    if not title.strip() and not description.strip():
        return None
    if PAID_PLACEHOLDER in title and PAID_PLACEHOLDER in description:
        return None

    # Strip placeholder values from any field
    def strip_placeholder(val):
        if isinstance(val, str) and PAID_PLACEHOLDER in val:
            return None
        return val

    country_raw = article.get("country")
    if isinstance(country_raw, list):
        # NewsData.io returns ["us"] — decode ISO code → full name
        country_code = country_raw[0] if country_raw else None
        country = CODE_TO_COUNTRY.get(country_code, country_code) if country_code else None
    elif isinstance(country_raw, str):
        # Other fetchers already provide the full country name
        country = country_raw
    else:
        country = None

    return {
        "article_id": article.get("article_id", ""),
        "title": title,
        "description": description,
        "link": article.get("link", ""),
        "image_url": strip_placeholder(article.get("image_url")),
        "video_url": strip_placeholder(article.get("video_url")),
        "source_name": article.get("source_name", ""),
        "source_icon": strip_placeholder(article.get("source_icon")),
        "country": country,
        "category": article.get("category") or [],
        "fetch_target": article.get("fetch_target") or "global",
        "keywords": article.get("keywords") or [],
        "pubDate": article.get("pubDate", ""),
        "language": article.get("language", ""),
    }


def _fetch_page(params: dict) -> list[dict]:
    """Call NewsData /latest and return the results list."""
    call_params = {**params, "apikey": settings.NEWSDATA_API_KEY, "language": "en"}
    log_params = {k: v for k, v in call_params.items() if k != "apikey"}
    try:
        resp = httpx.get(NEWSDATA_BASE, params=call_params, timeout=20)
        data = resp.json()
        if data.get("status") == "error":
            logger.warning("NewsData.io error for %s: %s", log_params, data.get("results"))
            return []
        return data.get("results") or []
    except Exception as exc:
        logger.warning("NewsData.io request failed for %s: %s", log_params, exc)
        return []


def _fetch_newsdata(user) -> list[dict]:
    """Pull from NewsData.io. Budget: ~18 calls / generation (200 req/day cap).

    Allocation:
      1  — country code (E layer)
      2  — country name + "country news" (E layer)
      2  — city exact phrase + city broad (N layer)
      1  — continent keyword (W layer)
      1  — trending/top-domain globally (S layer)
      5  — core global categories: world, business, technology, science, health (S layer)
      up to 6  — user topic keywords, high priority first (S layer)
    """
    country_code = COUNTRY_CODE_MAP.get(user.country, "")
    continent_keyword = CONTINENT_KEYWORDS.get(user.continent, user.continent)

    # All user topics (high first, then medium, then low) — used as keyword
    # searches so every stated interest gets direct coverage.
    all_tags = (
        [t.get("name") for t in (user.tags or []) if t.get("priority") == "high" and t.get("name")] +
        [t.get("name") for t in (user.tags or []) if t.get("priority") == "medium" and t.get("name")] +
        [t.get("name") for t in (user.tags or []) if t.get("priority") == "low" and t.get("name")]
    )
    tag_queries = all_tags[:6]

    raw: list[dict] = []

    def _add(articles: list[dict], target: str) -> None:
        for a in articles:
            a["fetch_target"] = target
        raw.extend(articles)

    if country_code:
        _add(_fetch_page({"country": country_code}), "national")
    _add(_fetch_page({"q": user.country}), "national")
    _add(_fetch_page({"q": f"{user.country} news"}), "national")
    _add(_fetch_page({"q": f'"{user.city}"'}), "local")
    _add(_fetch_page({"q": user.city}), "local")
    _add(_fetch_page({"q": continent_keyword}), "regional")
    _add(_fetch_page({"prioritydomain": "top"}), "global")
    _add(_fetch_page({"category": "world"}), "global")
    _add(_fetch_page({"category": "business"}), "global")
    _add(_fetch_page({"category": "technology"}), "global")
    _add(_fetch_page({"category": "science"}), "global")
    _add(_fetch_page({"category": "health"}), "global")
    for tag in tag_queries:
        _add(_fetch_page({"q": tag}), "global")
    return raw


def fetch_stories(
    user,
    use_newsdata: bool = True,
    use_newsapi: bool = True,
    use_newscatcher: bool = True,
    use_gnews: bool = True,
    use_guardian: bool = True,
    use_nytimes: bool = True,
    on_source_done=None,
) -> list[dict]:
    """
    Fetch and merge stories from all enabled news sources.
    Deduplicates by article_id, cleans, caps at 500 articles for downstream stages.

    Source budget per generation (intentionally generous — we want a big candidate
    pool so the per-layer bucketing has lots to choose from):
      NewsData   : ~18 calls (200/day,   ~11 gens/day)
      NewsAPI    : ~18 calls (100/day,   ~5  gens/day)
      NewsCatcher: 1 async CatchAll job  (reuses cached records when possible)
      GNews      : ~15 calls (100/day,   ~6  gens/day)
      Guardian   : ~36 calls (5,000/day, ~138 gens/day)
      NYTimes    : ~26 calls (4,000/day, ~153 gens/day)

    A typical generation finishes in 1–4 minutes depending on rate-limited
    sources (Guardian + GNews each throttle to 1 req/s).
    """
    from newsapi_fetcher import fetch_newsapi_stories
    from newscatcher_fetcher import fetch_newscatcher_stories
    from gnews_fetcher import fetch_gnews_stories
    from guardian_fetcher import fetch_guardian_stories
    from nytimes_fetcher import fetch_nytimes_stories

    # Map each enabled source to its fetcher function
    enabled: list[tuple[str, object]] = []
    if use_newsdata:    enabled.append(("newsdata",    _fetch_newsdata))
    if use_newsapi:     enabled.append(("newsapi",     fetch_newsapi_stories))
    if use_newscatcher: enabled.append(("newscatcher", fetch_newscatcher_stories))
    if use_gnews:       enabled.append(("gnews",       fetch_gnews_stories))
    if use_guardian:    enabled.append(("guardian",    fetch_guardian_stories))
    if use_nytimes:     enabled.append(("nytimes",     fetch_nytimes_stories))

    all_raw: list[dict] = []

    if not enabled:
        return []

    total_sources = len(enabled)
    completed_sources = 0

    # Run all source fetchers in parallel — dramatically reduces total fetch time
    with ThreadPoolExecutor(max_workers=total_sources) as executor:
        future_to_name = {
            executor.submit(fn, user): name
            for name, fn in enabled
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                all_raw += future.result()
            except Exception as exc:
                # Include the full traceback so a recurring source failure is
                # debuggable from logs alone (the fetch silently drops to []
                # for the affected source and the pipeline continues).
                logger.exception("Source '%s' raised an unexpected error: %s", name, exc)
            completed_sources += 1
            if on_source_done is not None:
                try:
                    on_source_done(name, completed_sources, total_sources)
                except Exception as exc:
                    logger.warning("on_source_done callback failed: %s", exc)

    seen_ids: set[str] = set()
    cleaned: list[dict] = []

    for raw in all_raw:
        article_id = raw.get("article_id", "")
        if not article_id or article_id in seen_ids:
            continue
        seen_ids.add(article_id)

        clean = _clean_article(raw)
        if clean:
            cleaned.append(clean)

    # Apply 3-day recency window: keep today, yesterday, and the day before
    cleaned = [a for a in cleaned if _is_within_3_days(a.get("pubDate", ""))]

    # Cap at 500. Python bucketing picks the best per layer; the writer never
    # sees more than the per-layer targets, so a large pool is free downstream.
    return cleaned[:500]


def fetch_local_boost(user, seen_ids: set[str]) -> list[dict]:
    """
    Gap-fill targeted fetch for N (city) and E (country) layers.
    Called when triage finds fewer than 10 articles for city or country.

    Uses Guardian (5 000/day) and NYTimes (4 000/day) most aggressively since
    they have the highest daily quotas. NewsData contributes one extra country call.

    Mutates `seen_ids` so internal duplicates are removed automatically.
    Returns already-cleaned articles that were NOT in seen_ids before this call.
    """
    from guardian_fetcher import _search as _guardian_search, _normalize as _guardian_normalize
    from nytimes_fetcher import _fetch_article_search as _nyt_search

    new_raw: list[dict] = []

    # ── Guardian boost ────────────────────────────────────────────────────────
    def _add_guardian(items: list[dict], category: str | None = None, country: str | None = None, fetch_target: str | None = None) -> None:
        for item in items:
            n = _guardian_normalize(item, category=category, country=country, fetch_target=fetch_target)
            if n:
                new_raw.append(n)

    # Country: larger page than the 15 used in the first pass
    _add_guardian(_guardian_search(q=user.country, page_size=30), category="national", country=user.country, fetch_target="national")
    # City: larger page
    _add_guardian(_guardian_search(q=user.city, page_size=25), category="local", country=user.country, fetch_target="local")
    # Continent keyword — lifts W layer too, which may promote to N/E if city/country appears
    continent_kw = {
        "Africa": "Africa", "Asia": "Asia", "Europe": "Europe",
        "North America": "Americas", "South America": "Latin America", "Oceania": "Pacific",
    }.get(user.continent, user.continent)
    if continent_kw:
        _add_guardian(_guardian_search(q=continent_kw, page_size=15), category="regional", fetch_target="regional")

    # ── NYTimes boost ─────────────────────────────────────────────────────────
    for art in _nyt_search(user.country, page_size=20, country=user.country, fetch_target="national"):
        new_raw.append(art)
    for art in _nyt_search(user.city, page_size=15, country=user.country, fetch_target="local"):
        new_raw.append(art)

    # ── NewsData boost (1 extra call — 200/day budget is tighter) ────────────
    country_code = COUNTRY_CODE_MAP.get(user.country, "")
    if country_code:
        boost_articles = _fetch_page({"country": country_code})
        for a in boost_articles:
            a["fetch_target"] = "national"
        new_raw += boost_articles

    # Deduplicate, clean, and apply 3-day recency window
    results: list[dict] = []
    for raw in new_raw:
        article_id = raw.get("article_id", "")
        if not article_id or article_id in seen_ids:
            continue
        seen_ids.add(article_id)
        clean = _clean_article(raw)
        if clean and _is_within_3_days(clean.get("pubDate", "")):
            results.append(clean)

    logger.info("fetch_local_boost: returned %d new articles", len(results))
    return results
