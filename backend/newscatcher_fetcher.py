import hashlib
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

NEWSCATCHER_SEARCH   = "https://api.newscatcherapi.com/v2/search"
NEWSCATCHER_LATEST   = "https://api.newscatcherapi.com/v2/latest_headlines"

# NewsCatcher topic values that map to our preset tags
TAG_TO_TOPIC: dict[str, str] = {
    "Technology":    "tech",
    "AI":            "tech",
    "Business":      "business",
    "Finance":       "finance",
    "Science":       "science",
    "Politics":      "politics",
    "Entertainment": "entertainment",
    "Sports":        "sport",
    "Travel":        "travel",
    "Food":          "food",
}

# ISO-2 (uppercase) → full country name
_CODE_TO_COUNTRY: dict[str, str] = {
    "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AR": "Argentina",
    "AM": "Armenia", "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan",
    "BH": "Bahrain", "BD": "Bangladesh", "BY": "Belarus", "BE": "Belgium",
    "BO": "Bolivia", "BA": "Bosnia and Herzegovina", "BW": "Botswana",
    "BR": "Brazil", "BN": "Brunei", "BG": "Bulgaria", "KH": "Cambodia",
    "CM": "Cameroon", "CA": "Canada", "CL": "Chile", "CN": "China",
    "CO": "Colombia", "CR": "Costa Rica", "HR": "Croatia", "CU": "Cuba",
    "CY": "Cyprus", "CZ": "Czech Republic", "DK": "Denmark", "DO": "Dominican Republic",
    "EC": "Ecuador", "EG": "Egypt", "EE": "Estonia", "ET": "Ethiopia",
    "FI": "Finland", "FR": "France", "GA": "Gabon", "GE": "Georgia",
    "DE": "Germany", "GH": "Ghana", "GR": "Greece", "GT": "Guatemala",
    "HN": "Honduras", "HU": "Hungary", "IS": "Iceland", "IN": "India",
    "ID": "Indonesia", "IR": "Iran", "IQ": "Iraq", "IE": "Ireland",
    "IL": "Israel", "IT": "Italy", "JM": "Jamaica", "JP": "Japan",
    "JO": "Jordan", "KZ": "Kazakhstan", "KE": "Kenya", "KW": "Kuwait",
    "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia", "LB": "Lebanon",
    "LR": "Liberia", "LY": "Libya", "LT": "Lithuania", "LU": "Luxembourg",
    "MG": "Madagascar", "MY": "Malaysia", "MV": "Maldives", "ML": "Mali",
    "MT": "Malta", "MU": "Mauritius", "MX": "Mexico", "MD": "Moldova",
    "MN": "Mongolia", "ME": "Montenegro", "MA": "Morocco", "MZ": "Mozambique",
    "MM": "Myanmar", "NA": "Namibia", "NP": "Nepal", "NL": "Netherlands",
    "NZ": "New Zealand", "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria",
    "KP": "North Korea", "MK": "North Macedonia", "NO": "Norway", "OM": "Oman",
    "PK": "Pakistan", "PA": "Panama", "PY": "Paraguay", "PE": "Peru",
    "PH": "Philippines", "PL": "Poland", "PT": "Portugal", "QA": "Qatar",
    "RO": "Romania", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia",
    "SN": "Senegal", "RS": "Serbia", "SG": "Singapore", "SK": "Slovakia",
    "SI": "Slovenia", "SO": "Somalia", "ZA": "South Africa", "KR": "South Korea",
    "SS": "South Sudan", "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan",
    "SE": "Sweden", "CH": "Switzerland", "SY": "Syria", "TW": "Taiwan",
    "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand", "TN": "Tunisia",
    "TR": "Turkey", "TM": "Turkmenistan", "UG": "Uganda", "UA": "Ukraine",
    "AE": "United Arab Emirates", "GB": "United Kingdom", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VE": "Venezuela", "VN": "Vietnam",
    "YE": "Yemen", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# Country name → uppercase ISO-2 (reverse of above)
_COUNTRY_TO_CODE: dict[str, str] = {v: k for k, v in _CODE_TO_COUNTRY.items()}


def _article_id(link: str) -> str:
    return "nc_" + hashlib.md5(link.encode()).hexdigest()


def _normalize(article: dict, fallback_country: str | None = None) -> dict | None:
    title = (article.get("title") or "").strip()
    excerpt = (article.get("excerpt") or article.get("summary") or "").strip()

    if not title and not excerpt:
        return None

    link = article.get("link") or ""
    if not link:
        return None

    # _id from NewsCatcher is a hex string — prefix once, never double-prefix
    raw_id = article.get("_id") or ""
    if raw_id and not raw_id.startswith("nc_"):
        article_id = f"nc_{raw_id}"
    elif raw_id:
        article_id = raw_id
    else:
        article_id = _article_id(link)

    # Country: NewsCatcher returns uppercase ISO-2 or full name depending on endpoint
    raw_country = article.get("country") or ""
    if len(raw_country) == 2:
        country = _CODE_TO_COUNTRY.get(raw_country.upper(), raw_country)
    elif raw_country:
        country = raw_country
    else:
        country = fallback_country

    topic = article.get("topic") or ""

    return {
        "article_id": article_id,
        "title": title,
        "description": excerpt,
        "link": link,
        "image_url": article.get("media") or None,
        "video_url": None,
        "source_name": article.get("clean_url") or "",
        "source_icon": None,
        "country": country,
        "category": [topic] if topic else [],
        "keywords": [],
        "pubDate": article.get("published_date") or "",
        "language": article.get("language") or "en",
    }


def _headers() -> dict[str, str]:
    return {"x-api-key": settings.NEWSCATCHER_API_KEY}


def _get(endpoint: str, params: dict) -> list[dict]:
    try:
        resp = httpx.get(endpoint, params=params, headers=_headers(), timeout=20)
        data = resp.json()
        if data.get("status") == "error":
            logger.warning("NewsCatcher error for %s: %s", params, data.get("message"))
            return []
        return data.get("articles") or []
    except Exception as exc:
        logger.warning("NewsCatcher request failed for %s: %s", params, exc)
        return []


def fetch_newscatcher_stories(user) -> list[dict]:
    """
    Fetch from NewsCatcher: latest headlines for country + topic,
    plus city keyword search.
    Max ~4 calls per report.
    """
    country_code = _COUNTRY_TO_CODE.get(user.country)
    all_raw: list[dict] = []

    # E layer: latest headlines for user's country
    if country_code:
        raw = _get(NEWSCATCHER_LATEST, {
            "countries": country_code,
            "lang": "en",
            "when": "24h",
            "page_size": 20,
        })
        for a in raw:
            n = _normalize(a, fallback_country=user.country)
            if n:
                all_raw.append(n)

    # N layer: city keyword search
    city_raw = _get(NEWSCATCHER_SEARCH, {
        "q": f'"{user.city}"',
        "lang": "en",
        "search_in": "title_summary",
        "sort_by": "date",
        "page_size": 15,
    })
    for a in city_raw:
        n = _normalize(a, fallback_country=user.country)
        if n:
            all_raw.append(n)

    # S/tag layer: up to 2 high-priority tags mapped to NewsCatcher topics
    high_tags = [t for t in user.tags if t.get("priority") == "high"][:2]
    for tag in high_tags:
        topic = TAG_TO_TOPIC.get(tag.get("name", ""))
        if topic:
            raw = _get(NEWSCATCHER_LATEST, {
                "topic": topic,
                "lang": "en",
                "when": "24h",
                "page_size": 15,
            })
        else:
            raw = _get(NEWSCATCHER_SEARCH, {
                "q": tag.get("name", ""),
                "lang": "en",
                "sort_by": "date",
                "page_size": 15,
            })
        for a in raw:
            n = _normalize(a, fallback_country=user.country)
            if n:
                all_raw.append(n)

    return all_raw
