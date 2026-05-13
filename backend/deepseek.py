import json
import logging
import re

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


def _summarize_response(response, label: str) -> dict:
    """Pull the diagnostic fields that explain why a DeepSeek call went wrong.

    Returned dict is logged AND attached to raised exceptions so that a failed
    job's `error_message` carries enough context to debug without rerunning.
    """
    info: dict[str, object] = {"label": label}
    try:
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""
        info["finish_reason"] = getattr(choice, "finish_reason", None)
        info["content_chars"] = len(content)
        info["content_head"] = content[:300]
        info["content_tail"] = content[-300:] if len(content) > 300 else ""
        # Reasoner-only: the model's chain of thought, separate from content.
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            info["reasoning_chars"] = len(reasoning)
        usage = getattr(response, "usage", None)
        if usage:
            info["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
            info["completion_tokens"] = getattr(usage, "completion_tokens", None)
            info["reasoning_tokens"] = getattr(usage, "reasoning_tokens", None)
            info["total_tokens"] = getattr(usage, "total_tokens", None)
    except Exception as exc:
        info["summarize_error"] = repr(exc)
    return info


def _summarize_messages(messages: list[dict]) -> dict:
    """Compact, log-safe view of the prompt that was sent."""
    out: dict[str, object] = {"message_count": len(messages)}
    total = 0
    for m in messages:
        content = m.get("content") or ""
        total += len(content)
    out["prompt_total_chars"] = total
    # Capture role-by-role char counts and a head/tail snippet of the user msg
    # (system prompts are static so we skip dumping them here).
    for m in messages:
        if m.get("role") == "user":
            content = m.get("content") or ""
            out["user_head"] = content[:400]
            out["user_tail"] = content[-200:] if len(content) > 400 else ""
            break
    return out


class DeepSeekError(RuntimeError):
    """Raised when a DeepSeek call returns something unusable.

    The exception's `args` carry a structured dict so the upstream worker can
    persist the full diagnostic context into job.error_message without needing
    to scrape logs.
    """
    def __init__(self, label: str, reason: str, **context):
        self.label = label
        self.reason = reason
        self.context = context
        super().__init__(f"DeepSeek {label} failed: {reason} | {context}")

client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)

SYSTEM_PROMPT = """You are a senior news editor building a personalised briefing. Articles have been classified into four geographic layers (N, E, W, S) by an AI triage system. Your job has three parts:

1) SELECT the best articles per layer, up to the `targets` count in the user message:
   - HIGH PRIORITY RULE for N and E: these layers must be as FULL as possible.
     Publish up to the target even if some articles are not breaking news — local events,
     background pieces, and soft news are all valid for N and E. Never leave N or E empty
     when candidates exist, even if the content feels routine.
   - For W and S: prefer impact, specificity, and non-redundancy.
   - Deduplicate: if two articles clearly cover the same EVENT, keep the one with the
     richer description or an image. Keep both if they cover different angles.
   - Do NOT move articles between layers.
   - Articles with `matched_tags` are more relevant to this reader — give them mild preference.

2) REWRITE each selected article as a card:
   - headline: punchy and clear, rewritten from the original title, no clickbait
   - hook: one sentence that creates interest
   - summary: 1-2 sentences based ONLY on what the title and description say. Do not invent facts.
   - tone_label: ONE of BREAKING, VIRAL, ANALYSIS, SIGNAL, INSIGHT, LIGHTHEARTED

   Tones:
     BREAKING — happening right now, fast-moving
     VIRAL — spreading fast, buzzy, high social interest
     ANALYSIS — expert opinion, deep reporting, investigation
     SIGNAL — early sign of a bigger trend
     INSIGHT — teaches something genuinely new
     LIGHTHEARTED — actually funny or heartwarming (only when it truly is)

3) WRITE report-level prose:
   - report_title: creative and specific to today's news mood, never generic
   - opening_line: 2-3 sentences, sharp and conversational, no name. Never say \"Here is your daily briefing.\"
   - closing_line: 1-2 sentences, reflective or observational, never preachy
   - Per layer a mood_line: ONE punchy sentence. If zero articles, set to \"Nothing notable here today.\"

Hard rules:
   - Every article_id in the output MUST come from the input. Never invent an article_id.
   - Each article_id may appear in AT MOST ONE layer.
   - Do NOT move articles between layers.

Return only valid JSON, no markdown, no backticks, no explanation:

{
  \"report_title\": \"string\",
  \"report_date\": \"ISO date\",
  \"opening_line\": \"string\",
  \"closing_line\": \"string\",
  \"sections\": {
    \"N\": {
      \"mood_line\": \"string\",
      \"stories\": [
        { \"article_id\": \"string\", \"headline\": \"string\", \"hook\": \"string\", \"summary\": \"string\", \"tone_label\": \"string\" }
      ]
    },
    \"E\": { \"mood_line\": \"string\", \"stories\": [...] },
    \"W\": { \"mood_line\": \"string\", \"stories\": [...] },
    \"S\": { \"mood_line\": \"string\", \"stories\": [...] }
  }
}

Never use: delve, crucial, groundbreaking, game-changer, it's worth noting, in conclusion, furthermore. Write like a sharp human editor. Summaries must never start with \"This article discusses.\"
"""

# ---------------------------------------------------------------------------
# Pass 1 — lightweight triage: classify articles into layers + score them
# ---------------------------------------------------------------------------

def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip()


def _repair_truncated_json(raw: str) -> str:
    """Best-effort repair for JSON cut off mid-string by an output token cap.

    Walks the string while tracking the bracket stack outside of strings.
    Finds the last position where it's safe to truncate (a top-of-stack comma,
    or the start of an incomplete object/array element), then closes any open
    structures so the result parses. Returns the same string unchanged if no
    safe trim point was found.
    """
    stack: list[str] = []          # current open brackets, e.g. ["{", "[", "{"]
    in_string = False
    escape = False
    safe_cut = 0                   # length of the longest prefix that's repair-friendly
    safe_stack: list[str] = []

    for i, ch in enumerate(raw):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

        # After processing this char, decide if it's a safe truncation point:
        # we are not inside a string and either a structural close just happened
        # or this is a comma at any depth (we can drop everything after it and
        # close the remaining open brackets).
        if not in_string and ch in (",", "}", "]"):
            safe_cut = i + (0 if ch == "," else 1)
            safe_stack = list(stack)

    if safe_cut == 0:
        return raw

    trimmed = raw[:safe_cut].rstrip(", \n\t\r")
    closing = "".join("}" if c == "{" else "]" for c in reversed(safe_stack))
    return trimmed + closing


def _safe_json_load(raw: str) -> dict:
    """Parse a JSON object; attempt a one-shot repair if the model truncated."""
    cleaned = _strip_fences(raw)
    if not cleaned:
        # Nothing to parse and nothing to repair — surface a precise error so
        # callers can attach diagnostic context (finish_reason, usage, etc.).
        raise json.JSONDecodeError("Empty response from DeepSeek", cleaned, 0)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(
            "DeepSeek JSON parse failed (%s); attempting truncation repair. content_head=%r content_tail=%r",
            exc, cleaned[:200], cleaned[-200:],
        )
        repaired = _repair_truncated_json(cleaned)
        return json.loads(repaired)  # if this still fails, surface to caller


# ---------------------------------------------------------------------------
# Deterministic bucketing — pure Python geo lookup. The AI used to do this
# job via triage, but it kept dumping non-continent articles into W instead of
# S — a country/continent lookup is a deterministic task the model shouldn't
# be guessing at. So we do it ourselves: layer + score are both computed here.
# ---------------------------------------------------------------------------

_VALID_LAYERS = ("N", "E", "W", "S")

# Country → continent. Mirrors the map in users_router. Kept in this module so
# the bucketing logic is self-contained and easy to update.
_CONTINENT_BY_COUNTRY: dict[str, str] = {
    "Afghanistan": "Asia", "Albania": "Europe", "Algeria": "Africa",
    "Argentina": "South America", "Armenia": "Asia", "Australia": "Oceania",
    "Austria": "Europe", "Azerbaijan": "Asia", "Bahrain": "Asia",
    "Bangladesh": "Asia", "Belarus": "Europe", "Belgium": "Europe",
    "Bolivia": "South America", "Bosnia and Herzegovina": "Europe",
    "Botswana": "Africa", "Brazil": "South America", "Bulgaria": "Europe",
    "Cambodia": "Asia", "Cameroon": "Africa", "Canada": "North America",
    "Chile": "South America", "China": "Asia", "Colombia": "South America",
    "Croatia": "Europe", "Cuba": "North America", "Czech Republic": "Europe",
    "Denmark": "Europe", "Dominican Republic": "North America", "Ecuador": "South America",
    "Egypt": "Africa", "Estonia": "Europe", "Ethiopia": "Africa", "Finland": "Europe",
    "France": "Europe", "Georgia": "Asia", "Germany": "Europe", "Ghana": "Africa",
    "Greece": "Europe", "Hungary": "Europe", "Iceland": "Europe", "India": "Asia",
    "Indonesia": "Asia", "Iran": "Asia", "Iraq": "Asia", "Ireland": "Europe",
    "Israel": "Asia", "Italy": "Europe", "Japan": "Asia", "Jordan": "Asia",
    "Kazakhstan": "Asia", "Kenya": "Africa", "Kuwait": "Asia", "Latvia": "Europe",
    "Lebanon": "Asia", "Libya": "Africa", "Lithuania": "Europe", "Luxembourg": "Europe",
    "Malaysia": "Asia", "Malta": "Europe", "Mexico": "North America", "Moldova": "Europe",
    "Mongolia": "Asia", "Montenegro": "Europe", "Morocco": "Africa", "Myanmar": "Asia",
    "Nepal": "Asia", "Netherlands": "Europe", "New Zealand": "Oceania",
    "Nigeria": "Africa", "North Korea": "Asia", "North Macedonia": "Europe",
    "Norway": "Europe", "Oman": "Asia", "Pakistan": "Asia", "Panama": "North America",
    "Paraguay": "South America", "Peru": "South America", "Philippines": "Asia",
    "Poland": "Europe", "Portugal": "Europe", "Qatar": "Asia", "Romania": "Europe",
    "Russia": "Europe", "Saudi Arabia": "Asia", "Senegal": "Africa", "Serbia": "Europe",
    "Singapore": "Asia", "Slovakia": "Europe", "Slovenia": "Europe", "Somalia": "Africa",
    "South Africa": "Africa", "South Korea": "Asia", "Spain": "Europe",
    "Sri Lanka": "Asia", "Sudan": "Africa", "Sweden": "Europe", "Switzerland": "Europe",
    "Syria": "Asia", "Taiwan": "Asia", "Tanzania": "Africa", "Thailand": "Asia",
    "Tunisia": "Africa", "Turkey": "Asia", "Uganda": "Africa", "Ukraine": "Europe",
    "United Arab Emirates": "Asia", "United Kingdom": "Europe",
    "United States": "North America", "Uruguay": "South America",
    "Venezuela": "South America", "Vietnam": "Asia", "Yemen": "Asia",
    "Zambia": "Africa", "Zimbabwe": "Africa",
}

# Common name variants we see in fetcher output. Mapped to the canonical name
# in _CONTINENT_BY_COUNTRY so layer assignment doesn't get tripped up by case
# or punctuation differences.
_COUNTRY_ALIASES: dict[str, str] = {
    "united states of america": "United States",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "uae": "United Arab Emirates",
    "korea, republic of": "South Korea",
    "korea": "South Korea",
    "russian federation": "Russia",
}

# Categories that are inherently global. An article tagged any of these goes
# straight to S regardless of its country — same rule the old AI prompt had.
_GLOBAL_CATEGORIES = {
    "technology", "tech", "ai", "artificial intelligence", "cybersecurity",
    "security", "science", "space",
}

# Demonyms / adjectives so the text rule catches "Tanzanian president" not just
# "Tanzania president". Only the most common forms — anything unusual just falls
# through to the country tag fallback.
_COUNTRY_ADJECTIVES: dict[str, list[str]] = {
    "United States": ["american", "u.s.", "u.s.a."],
    "United Kingdom": ["british", "uk", "u.k."],
    "Tanzania": ["tanzanian"],
    "Kenya": ["kenyan"],
    "Uganda": ["ugandan"],
    "Rwanda": ["rwandan"],
    "Nigeria": ["nigerian"],
    "Ghana": ["ghanaian"],
    "South Africa": ["south african"],
    "Egypt": ["egyptian"],
    "Morocco": ["moroccan"],
    "Ethiopia": ["ethiopian"],
    "China": ["chinese"],
    "Japan": ["japanese"],
    "India": ["indian"],
    "Russia": ["russian"],
    "Germany": ["german"],
    "France": ["french"],
    "Italy": ["italian"],
    "Spain": ["spanish"],
    "Brazil": ["brazilian"],
    "Mexico": ["mexican"],
    "Canada": ["canadian"],
    "Australia": ["australian"],
}

_CONTINENT_ADJECTIVES: dict[str, list[str]] = {
    "Africa": ["african", "africans"],
    "Asia": ["asian", "asians"],
    "Europe": ["european", "europeans"],
    "North America": ["north american"],
    "South America": ["south american", "latin american"],
    "Oceania": ["oceanic", "pacific"],
}


def _normalize_country(raw: str | None) -> str:
    """Return the canonical country name, or '' if unknown.

    Handles common case/punctuation variants ("united states of america" →
    "United States") so country→continent lookups succeed regardless of which
    fetcher emitted the article.
    """
    if not raw:
        return ""
    cleaned = raw.strip()
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[lower]
    # Case-insensitive match against the canonical map
    for canonical in _CONTINENT_BY_COUNTRY:
        if canonical.lower() == lower:
            return canonical
    return cleaned  # unknown — return as-is for logging, won't match anyway


def _continent_of(country: str) -> str:
    """Continent for the canonical country name, or '' if unknown."""
    return _CONTINENT_BY_COUNTRY.get(country, "")


def _word_in(text: str, term: str) -> bool:
    """Whole-word case-insensitive match (so 'Iran' doesn't match 'Iranian').

    A plain `in` check would put articles about 'iranian elections' into the
    Iran bucket even when the user is in 'iraq' (or vice versa), so we anchor
    with simple non-letter boundaries.
    """
    if not term or not text:
        return False
    pattern = r"(?<![a-z])" + re.escape(term.lower()) + r"(?![a-z])"
    return bool(re.search(pattern, text))


def _continent_country_terms(continent: str, exclude: str | None = None) -> list[str]:
    """All country names + adjectives on a given continent, excluding one country.

    Used to detect "this article is about another country on my continent" so
    e.g. a Tanzanian user gets Kenya/Uganda stories routed to W (continent).
    """
    terms: list[str] = []
    for country, cont in _CONTINENT_BY_COUNTRY.items():
        if cont != continent or country == exclude:
            continue
        terms.append(country.lower())
        terms.extend(a.lower() for a in _COUNTRY_ADJECTIVES.get(country, []))
    return terms


def _assign_layer(article: dict, user) -> str:
    """Pick N/E/W/S — text-first, with smarter fallbacks.

    N and E always take priority over global-topic categories. A Tanzanian
    tech-startup article tagged 'technology' should be E, not S.

    Rules (in order):
      N — user's city named in title/desc
          OR fetcher tagged it "local" AND article country = user's country
      E — user's country (or its adjective) named in title/desc
          OR article country tag == user's country and not a global topic
      S — global topic (tech/AI/science/space), checked AFTER N/E
      W — continent/adjective named in title/desc,
          OR another country on the same continent named in title/desc,
          OR article country tag is a continent neighbour
      S — fallback
    """
    title_desc = ((article.get("title") or "") + " " + (article.get("description") or "")).lower()
    article_cats_lower = [c.lower() for c in (article.get("category") or [])]
    categories_str = " ".join(article_cats_lower)
    keywords_str = " ".join(article.get("keywords") or []).lower()
    topic_haystack = f"{categories_str} {keywords_str}"

    user_city = (user.city or "").strip()
    user_country = (user.country or "").strip()
    user_continent = (user.continent or "").strip()
    article_country = _normalize_country(article.get("country"))

    # ── N: city named in text ─────────────────────────────────────────────────
    if user_city and _word_in(title_desc, user_city):
        return "N"

    # ── N: fetcher explicitly tagged this as a local city result ─────────────
    # Fetchers set category="local" only on city-targeted searches.
    if "local" in article_cats_lower and article_country == user_country:
        return "N"

    # ── E: country named in text ──────────────────────────────────────────────
    country_terms = [user_country.lower()] + [
        a.lower() for a in _COUNTRY_ADJECTIVES.get(user_country, [])
    ]
    if any(_word_in(title_desc, t) for t in country_terms if t):
        return "E"

    # ── E: country tag matches + no other continent-country in the text ───────────
    # Fetchers stamp country=user.country on ALL results from country/city queries,
    # even articles that are primarily about a neighbouring country. The text check
    # above already caught articles that name the country. This fallback handles
    # articles that don't repeat the country name but were fetched by a country
    # search. Guard: if a neighbour's name appears in text, this is a W article.
    is_global_topic = any(t in topic_haystack for t in _GLOBAL_CATEGORIES)
    if article_country == user_country and not is_global_topic and "local" not in article_cats_lower:
        neighbor_terms = _continent_country_terms(user_continent, exclude=user_country)
        has_neighbour_in_text = any(_word_in(title_desc, t) for t in neighbor_terms)
        if not has_neighbour_in_text:
            return "E"

    # ── S: pure global topic (after N/E have had their chance) ───────────────
    if is_global_topic:
        return "S"

    # ── W: continent name / adjective in text ────────────────────────────────
    continent_terms = [user_continent.lower()] + [
        a.lower() for a in _CONTINENT_ADJECTIVES.get(user_continent, [])
    ]
    if any(_word_in(title_desc, t) for t in continent_terms if t):
        return "W"
    for term in _continent_country_terms(user_continent, exclude=user_country):
        if _word_in(title_desc, term):
            return "W"

    # ── W: article country tag is a continent neighbour ───────────────────────
    if article_country and article_country != user_country:
        if _continent_of(article_country) == user_continent:
            return "W"

    return "S"


# ---------------------------------------------------------------------------
# AI triage — one DeepSeek-chat call classifies all articles by content,
# overcoming the limits of pure text-matching for N/E layer assignment.
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = """\
You are a geographic news classifier. Classify each article into one layer.

User location:
  City      = the city they live in (may be small, rural, or not well-known globally)
  Country   = their country
  Continent = their continent

Each article has these fields:
  article_id       — unique ID (use as output key)
  title            — article headline
  description      — article summary
  fetch_layer_hint — which layer this article was fetched for:
                     "local"    = fetched by a CITY-targeted search → strong signal for N
                     "national" = fetched by a COUNTRY-targeted search → strong signal for E
                     "regional" = fetched by a CONTINENT-targeted search → strong signal for W
                     "global"   = fetched from a global topic section → likely W or S

Layer definitions (N > E > W > S priority — always assign the most local layer that fits):

  N — CITY layer. Bias strongly toward N.
      • ALWAYS assign N when fetch_layer_hint is "local" UNLESS the title/description
        clearly names a different city or a national/global event.
      • Assign N if the city name appears anywhere in title or description.
      • Local news (crime, infrastructure, local politics, community events) that is
        plausibly in or near the city even without an explicit city mention.

  E — COUNTRY layer. Bias strongly toward E.
      • ALWAYS assign E when fetch_layer_hint is "national" UNLESS the title/description
        clearly names a DIFFERENT country as the primary subject.
      • Assign E if the country name or a national institution appears anywhere.
      • National politics, economy, domestic sport/culture → E even with international angles.
      • When in doubt between E and W, choose E.
      • When in doubt between E and S, choose E unless clearly global.

  W — CONTINENT layer.
      • Another country on the same continent, or a continental/regional body.

  S — WORLD layer (last resort).
      • Other continents, truly global stories, space, generic worldwide tech.

Return ONLY a flat JSON object: article_id → layer letter. No explanation.
Example: {"a1b2c3": "N", "d4e5f6": "E", "g7h8i9": "S"}
"""


def triage_articles_with_ai(user, articles: list[dict]) -> dict[str, str]:
    """Classify all articles into N/E/W/S with a DeepSeek-chat call per batch.

    Returns {article_id: layer}. Gracefully returns {} on total failure so
    callers fall back to "S" (world) for unclassified articles.

    BATCH_SIZE is kept small so each response comfortably fits in max_tokens.
    Each article ID is a 32-char hex string that tokenises at ~25 tokens per
    output line; 100 articles × 25 ≈ 2,500 output tokens, well within 4,096.
    """
    if not articles:
        return {}

    BATCH_SIZE = 100   # 100 × ~25 output tokens/article = ~2,500 tokens, safe within 4,096
    result: dict[str, str] = {}

    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start: batch_start + BATCH_SIZE]

        compact = [
            {
                "article_id": a["article_id"],
                "title": (a.get("title") or "")[:120],
                "description": (a.get("description") or "")[:150],
                # Hint to triage: which layer this article was fetched for.
                # "local"=city search, "national"=country search, "regional"=continent.
                "fetch_layer_hint": a.get("fetch_target", ""),
            }
            for a in batch
        ]

        user_message = (
            f"City: {user.city} | Country: {user.country} | Continent: {user.continent}\n\n"
            f"Articles:\n{json.dumps(compact, ensure_ascii=False)}"
        )

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": _TRIAGE_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            data = _safe_json_load(raw)
            # Accept only valid layer codes; ignore anything else
            valid = {k: v for k, v in data.items() if v in ("N", "E", "W", "S")}
            result.update(valid)
        except Exception as exc:
            logger.warning(
                "AI triage batch %d–%d failed (falling back to deterministic): %s",
                batch_start, batch_start + len(batch), exc,
            )

    n = sum(1 for v in result.values() if v == "N")
    e = sum(1 for v in result.values() if v == "E")
    w = sum(1 for v in result.values() if v == "W")
    s = sum(1 for v in result.values() if v == "S")
    logger.info(
        "AI triage complete: %d/%d classified — N=%d E=%d W=%d S=%d",
        len(result), len(articles), n, e, w, s,
    )
    return result


def _matched_tags(story: dict, user_tags: list[dict]) -> list[str]:
    """Return the user's tags whose name appears anywhere in the article's text.

    Used both for the matched_tags display field and as a scoring signal.
    Case-insensitive substring match across title/desc/keywords/category.
    """
    haystack = " ".join([
        story.get("title") or "",
        story.get("description") or "",
        " ".join(story.get("keywords") or []),
        " ".join(story.get("category") or []),
    ]).lower()
    return [
        t["name"] for t in (user_tags or [])
        if t.get("name") and t["name"].lower() in haystack
    ]


def _score_article(article: dict, user_tags: list[dict]) -> float:
    """Deterministic 0–1 relevance score. Mirrors what the AI used to compute.

    Baseline 0.2 keeps unrelated-but-clean articles eligible (so empty user-tag
    profiles don't end up with an empty briefing). Tag matches, recency, and a
    cover image all bump it up.
    """
    haystack = " ".join([
        article.get("title") or "",
        article.get("description") or "",
        " ".join(article.get("category") or []),
        " ".join(article.get("keywords") or []),
    ]).lower()

    score = 0.20
    for tag in user_tags or []:
        name = (tag.get("name") or "").lower()
        if not name or name not in haystack:
            continue
        priority = tag.get("priority", "medium")
        score += {"high": 0.40, "medium": 0.20, "low": 0.10}.get(priority, 0.20)

    if article.get("image_url"):
        score += 0.05

    pub = article.get("pubDate") or ""
    if pub and _published_within_hours(pub, 12):
        score += 0.10

    return min(1.0, score)


def _published_within_hours(pub_iso: str, hours: int) -> bool:
    """True if pub_iso parses and is within the last `hours`. Lenient on parse errors."""
    if not pub_iso:
        return False
    try:
        from datetime import datetime, timezone, timedelta
        normalized = pub_iso.strip().replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) <= timedelta(hours=hours)
    except (ValueError, TypeError):
        return False


def _is_blocked(story: dict, blocked_words: list[str]) -> bool:
    """True if any blocked word appears in title or description (case-insensitive)."""
    if not blocked_words:
        return False
    title = (story.get("title") or "").lower()
    desc = (story.get("description") or "").lower()
    haystack = f"{title} {desc}"
    return any(w.lower() in haystack for w in blocked_words if w)


def bucket_stories(
    user,
    stories: list[dict],
    targets: dict[str, int],
    ai_layers: dict[str, str] | None = None,
) -> dict[str, list[dict]]:
    """Group stories into N/E/W/S and cap each layer.

    Layer assignment prefers `ai_layers` (from `triage_articles_with_ai`) when
    available. Articles not classified by AI default to "S" (world).
    Scoring is a small mechanical sum over tag matches, recency, and image.
    The writer downstream only writes prose — it cannot drop or re-route layers.
    """
    blocked = user.blocked_words or []
    user_tags = user.tags or []
    ai_layers = ai_layers or {}

    buckets: dict[str, list[dict]] = {k: [] for k in _VALID_LAYERS}

    for s in stories:
        if _is_blocked(s, blocked):
            continue

        # AI classification wins; unclassified articles default to S (world).
        # No deterministic fallback — the user preference is AI-only classification.
        aid = s.get("article_id", "")
        layer = ai_layers.get(aid) or "S"
        score = _score_article(s, user_tags)

        # N and E articles get a floor score so they always make the pool
        # regardless of tag matches. A user in a small city has no tags that
        # mention their town — without this boost those articles would all
        # score 0.20 and get cut before the writer ever sees them.
        if layer == "N":
            score = max(score, 0.60)
        elif layer == "E":
            score = max(score, 0.45)

        enriched = dict(s)
        enriched["matched_tags"] = _matched_tags(s, user_tags)
        enriched["relevance_score"] = round(score, 3)
        enriched["layer"] = layer
        buckets[layer].append(enriched)

    # Sort each layer by score desc and cap at the per-layer target.
    for layer in _VALID_LAYERS:
        buckets[layer].sort(key=lambda s: s.get("relevance_score", 0.0), reverse=True)
        cap = max(0, int(targets.get(layer, 10)))
        buckets[layer] = buckets[layer][:cap]

    return buckets


def _layer_label(layer: str, user) -> str:
    return {
        "N": f"Narrow · {user.city}",
        "E": f"Expanded · {user.country}",
        "W": f"Wide · {user.continent}",
        "S": "Sweeping · World",
    }.get(layer, layer)


def _empty_section(layer: str, user) -> dict:
    return {
        "label": _layer_label(layer, user),
        "mood_line": "Nothing notable here today.",
        "stories": [],
    }


def _writer_payload(user, buckets: dict[str, list[dict]], targets: dict[str, int]) -> dict:
    """Build the compact payload sent to the writer.

    Sends a candidate pool that is larger than the final target count — the
    writer AI selects the best articles per layer and rewrites them.
    We deliberately do NOT include the `country` metadata field: fetchers stamp
    country = user.country on city/country searches, which would mislead the
    writer. Title + description are the truth source.
    """
    flat: list[dict] = []
    for layer in _VALID_LAYERS:
        for s in buckets.get(layer, []):
            flat.append({
                "article_id": s["article_id"],
                "current_layer": layer,
                "title": s.get("title", ""),
                "description": (s.get("description") or "")[:400],
                "matched_tags": s.get("matched_tags", []),
            })
    return {
        "user_profile": {
            "city": user.city,
            "country": user.country,
            "continent": user.continent,
        },
        "targets": targets,
        "layers": {
            "N": f"Narrow — stories specifically about {user.city}",
            "E": f"Expanded — stories specifically about {user.country} as a nation (NOT continent-wide)",
            "W": f"Wide — stories about {user.continent} or other countries on {user.continent}",
            "S": "Sweeping — world / global / other continents",
        },
        "articles": flat,
    }


def _merge_writer_output(
    user,
    buckets: dict[str, list[dict]],
    writer: dict,
) -> dict:
    """Combine the writer's prose with passthrough source fields.

    The writer's only job is to rewrite headlines/hooks/summaries and deduplicate.
    Layer placement is fixed by AI triage — the writer is instructed not to move
    articles. We still accept an article under whichever layer the writer emits
    it in (for robustness), but only for article_ids that came from the input.
    Any invented id is silently discarded. If the writer returns ZERO stories for
    a layer that Python had populated, we restore Python's picks so a model
    misfire can never empty the briefing.
    """
    # Flat lookup across all input layers so we can honour layer-moves
    by_id: dict[str, dict] = {}
    for layer in _VALID_LAYERS:
        for s in buckets.get(layer, []):
            by_id[s["article_id"]] = s

    writer_sections = writer.get("sections") or {}
    out_sections: dict[str, dict] = {}
    placed_ids: set[str] = set()

    for layer in _VALID_LAYERS:
        ws = writer_sections.get(layer) or {}
        writer_stories = ws.get("stories") or []

        out_stories: list[dict] = []
        for prose in writer_stories:
            aid = prose.get("article_id")
            source = by_id.get(aid) if aid else None
            if not source or aid in placed_ids:
                # Hallucinated id or already placed in another layer — skip.
                continue
            placed_ids.add(aid)
            out_stories.append(_make_story(source, prose, layer))

        # Safety fallback: if Python had stories here but the AI returned none,
        # restore Python's picks (without prose — they'll show the raw title).
        python_picks = buckets.get(layer, [])
        if not out_stories and python_picks:
            logger.warning(
                "AI returned empty %s layer despite %d Python picks — falling back to Python",
                layer, len(python_picks),
            )
            for source in python_picks:
                if source["article_id"] in placed_ids:
                    continue
                placed_ids.add(source["article_id"])
                out_stories.append(_make_story(source, {}, layer))

        out_sections[layer] = {
            "label": _layer_label(layer, user),
            "mood_line": ws.get("mood_line") or (
                "Nothing notable here today." if not out_stories else ""
            ),
            "stories": out_stories,
        }

    return {
        "report_title": writer.get("report_title") or "Today's Briefing",
        "opening_line": writer.get("opening_line") or "",
        "closing_line": writer.get("closing_line") or "",
        "sections": out_sections,
    }


def _make_story(source: dict, prose: dict, layer: str) -> dict:
    """Assemble one card by merging AI prose with passthrough source fields."""
    return {
        "article_id": source["article_id"],
        "headline": prose.get("headline") or source.get("title", ""),
        "hook": prose.get("hook") or "",
        "summary": prose.get("summary") or (source.get("description") or "")[:240],
        "tone_label": prose.get("tone_label") or "INSIGHT",
        "url": source.get("link", ""),
        "source_name": source.get("source_name", ""),
        "source_icon": source.get("source_icon"),
        "image_url": source.get("image_url"),
        "video_url": source.get("video_url"),
        "matched_tags": source.get("matched_tags", []),
        "relevance_score": source.get("relevance_score", 0.3),
        "layer": layer,
        "category": source.get("category", []),
        "published_at": source.get("pubDate", ""),
    }


def generate_report(
    user,
    stories: list[dict],
    temperature: float = 0.7,
    targets: dict[str, int] | None = None,
    on_progress=None,
) -> tuple[dict, str]:
    """Triage articles with AI, bucket them, then ask DeepSeek to write prose.

    Pipeline:
      1. AI triage  — classify all articles into N/E/W/S via a single
                      deepseek-chat call. Falls back to deterministic per-article
                      if the call fails.
      2. Bucket     — group into layers, score, sort, cap per-layer target.
      3. Write      — deepseek-chat rewrites headlines/hooks/summaries and
                      generates the report-level prose.

    `on_progress(stage, pct)` is called at key milestones if provided.
    """
    targets = targets or {"N": 15, "E": 15, "W": 10, "S": 40}

    # ── Step 1: AI triage ─────────────────────────────────────────────────────
    if on_progress:
        on_progress("triaging", 65)
    ai_layers = triage_articles_with_ai(user, stories)

    # ── Step 2: Bucket ────────────────────────────────────────────────────────
    # Build a candidate pool sent to the writer AI. N and E are uncapped —
    # every article triage assigned there is passed through so the writer
    # never misses city/country news (critical for small/remote towns).
    # W and S have generous but bounded caps to keep token usage predictable.
    pool_targets = {
        "N": len(stories),          # uncapped — keep ALL city articles
        "E": len(stories),          # uncapped — keep ALL country articles
        "W": min(targets["W"] * 4, 80),
        "S": min(targets["S"] * 4, 200),
    }
    buckets = bucket_stories(user, stories, pool_targets, ai_layers=ai_layers)
    logger.info(
        "Pool counts for user=%s — N=%d E=%d W=%d S=%d (in: %d stories, ai_classified: %d, targets: %s)",
        getattr(user, "id", "?"),
        len(buckets["N"]), len(buckets["E"]), len(buckets["W"]), len(buckets["S"]),
        len(stories), len(ai_layers), targets,
    )

    # If literally every layer is empty there's nothing to write. Return a
    # structurally-valid empty report so the UI still renders.
    if not any(buckets.values()):
        return {
            "report_title": "A quiet day on the wire.",
            "opening_line": "Nothing crossed the wire today that matches your filters.",
            "closing_line": "Check back tomorrow.",
            "sections": {layer: _empty_section(layer, user) for layer in _VALID_LAYERS},
        }, ""

    # ── Step 3: Write ─────────────────────────────────────────────────────────
    if on_progress:
        on_progress("writing", 75)

    user_message = json.dumps(_writer_payload(user, buckets, targets), ensure_ascii=False)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            max_tokens=12288,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.exception("DeepSeek writer request failed: %s", exc)
        raise DeepSeekError(
            "generate_report",
            f"API request failed: {exc.__class__.__name__}: {exc}",
            prompt=_summarize_messages(messages),
        )

    summary = _summarize_response(response, "generate_report")
    logger.info(
        "DeepSeek generate — prompt_tokens=%s completion=%s finish=%s content_chars=%s",
        summary.get("prompt_tokens"), summary.get("completion_tokens"),
        summary.get("finish_reason"), summary.get("content_chars"),
    )

    raw = response.choices[0].message.content or ""
    if not raw.strip():
        logger.error(
            "DeepSeek writer returned EMPTY content. response=%s prompt=%s",
            summary, _summarize_messages(messages),
        )
        raise DeepSeekError(
            "generate_report",
            "empty content from model — possibly hit content filter or token cap",
            finish_reason=summary.get("finish_reason"),
            completion_tokens=summary.get("completion_tokens"),
            prompt_tokens=summary.get("prompt_tokens"),
        )

    try:
        parsed = _safe_json_load(raw)
        merged = _merge_writer_output(user, buckets, parsed)
        # Compare Python-bucketed vs AI-finalised counts so a regression is
        # visible in logs without rerunning the job.
        py = {k: len(v) for k, v in buckets.items()}
        ai = {k: len(merged["sections"][k]["stories"]) for k in _VALID_LAYERS}
        logger.info(
            "Writer selected — pool=N%d/E%d/W%d/S%d  →  final=N%d/E%d/W%d/S%d",
            py["N"], py["E"], py["W"], py["S"],
            ai["N"], ai["E"], ai["W"], ai["S"],
        )
        return merged, raw
    except Exception as exc:
        logger.error(
            "DeepSeek writer JSON parse failed (%s). response=%s prompt=%s",
            exc, summary, _summarize_messages(messages),
        )
        raise DeepSeekError(
            "generate_report",
            f"JSON parse failed: {exc.__class__.__name__}: {exc}",
            finish_reason=summary.get("finish_reason"),
            content_head=summary.get("content_head"),
            content_tail=summary.get("content_tail"),
            content_chars=summary.get("content_chars"),
        )
