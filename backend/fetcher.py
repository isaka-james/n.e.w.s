import logging
import httpx
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

    country_raw = article.get("country") or []
    country_code = country_raw[0] if country_raw else None
    # Decode ISO code → full name so DeepSeek can compare against user.country
    country = CODE_TO_COUNTRY.get(country_code, country_code) if country_code else None

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
    """Pull from NewsData.io across all four geographic layers."""
    country_code = COUNTRY_CODE_MAP.get(user.country, "")
    continent_keyword = CONTINENT_KEYWORDS.get(user.continent, user.continent)
    high_tags = [t["name"] for t in user.tags if t.get("priority") == "high"][:3]

    raw: list[dict] = []
    if country_code:
        raw += _fetch_page({"country": country_code})
    raw += _fetch_page({"q": user.city})
    raw += _fetch_page({"q": continent_keyword})
    for tag in high_tags:
        raw += _fetch_page({"q": tag})
    return raw


def fetch_stories(
    user,
    use_newsdata: bool = True,
    use_newsapi: bool = True,
    use_newscatcher: bool = True,
) -> list[dict]:
    """
    Fetch and merge stories from all enabled news sources.
    Deduplicates by article_id, cleans, caps at 60 for DeepSeek.
    """
    from newsapi_fetcher import fetch_newsapi_stories
    from newscatcher_fetcher import fetch_newscatcher_stories

    all_raw: list[dict] = []
    if use_newsdata:
        all_raw += _fetch_newsdata(user)
    if use_newsapi:
        all_raw += fetch_newsapi_stories(user)
    if use_newscatcher:
        all_raw += fetch_newscatcher_stories(user)

    seen_ids: set[str] = set()
    cleaned: list[dict] = []

    for raw in all_raw:
        article_id = raw.get("article_id", "")
        if article_id in seen_ids:
            continue
        seen_ids.add(article_id)

        clean = _clean_article(raw)
        if clean:
            cleaned.append(clean)

    # Cap at 60 to keep the DeepSeek payload manageable
    return cleaned[:60]
