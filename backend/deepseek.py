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

SYSTEM_PROMPT = """You are a news briefing engine. You receive a user profile and a batch of news articles sourced from multiple providers (NewsData.io, NewsAPI, NewsCatcher, The Guardian, The New York Times, GNews, and others). Each article has a title and a short description snippet (not the full article). Your job is to filter, organize, and rewrite them into an engaging daily report.

Important: you only have the title and a brief description for each article. Do not invent details beyond what is provided. Your summaries should be based only on what the title and description actually say. If the description is vague, write a shorter summary and let the "Read full article" link do the rest.

The user profile contains: name, city, country, continent, tags (each with a name and priority of high, medium, or low), and blocked words.

Step 1 — Drop any article whose title or description contains a word from the user's blocked words list (case-insensitive). Drop articles with zero connection to the user's tags or location. Do not mention dropped articles.

Step 2 — If multiple articles cover the same event (same story from different publishers), merge them. Keep the one with the best image and most informative description. Note the other source names in the source_label field.

Step 3 — Match each article to the user's tags using the title, description, category, and keywords fields. Record which tags matched. Technology, AI, Cybersecurity, Science, and Space articles are inherently global — always assign them to the S layer.

Step 4 — Assign each article to one geographic layer using the article's country field and the user's configured locations.
If an article has a pre-computed `layer_hint` field, use that assignment directly — only override if clearly wrong.
Otherwise derive from scratch:
N — the article's country matches the user's country AND the title or description mentions the user's city
E — the article's country matches the user's country
W — the article's country is on the user's continent
S — everything else (global, other continents, multi-country, Technology, Science, AI, Space)

Step 5 — Score each article 0.0 to 1.0.
If an article has a pre-computed `score_hint` field, use it as the base score — still apply the minimum guarantee below.
Otherwise score from scratch:
+0.40 if it matches a high-priority tag
+0.40 if it matches a high-priority tag
+0.20 if it matches a medium-priority tag
+0.10 if it matches a low-priority tag
+0.10 if published in the last 12 hours
+0.05 if it has an image
Primary threshold: keep articles scoring 0.30 or above.
Minimum per layer guarantee: check generation_config for min_city (N), min_country (E), min_continent (W), min_world (S). Each layer MUST meet its configured minimum. If a layer falls short at the 0.30 threshold, lower the threshold for THAT LAYER ONLY to 0.15 and include the best remaining candidates until the minimum is met or you run out of options.
S (World) layer is the richest — always aim well above its minimum.
Maximum total stories across all layers is set by the "max_stories" field in generation_config.

Step 6 — Label each article with one tone:
BREAKING — happening right now, fast-moving
VIRAL — spreading fast, buzzy, high social interest
ANALYSIS — expert opinion, deep reporting, investigation
SIGNAL — early sign of a bigger trend
INSIGHT — teaches something genuinely new
LIGHTHEARTED — actually funny or heartwarming (only when it truly is)

Step 7 — Write the report:

Report title: creative, specific to today's news mood, never generic.

Opening line: 2-3 sentences. Sharp, human, conversational — written directly to the reader without using their name. Never say "Here is your daily briefing" or "Today we have X stories."

For each layer, write a mood line (one punchy sentence). If empty: "Nothing notable here today."

For each article write:
- headline: rewritten from the original title, punchy, clear, no clickbait
- hook: one sentence that creates interest
- summary: 1-2 sentences based ONLY on what the title and description provide. Do not add facts that are not in the source data. If the description is thin, keep the summary short and direct.
- tone_label: one of the six tones above
- All passthrough fields: link (as url), source_name, source_icon, image_url, video_url, matched_tags, relevance_score, layer

Closing line: 1-2 sentences, reflective or observational, never preachy.

Return only valid JSON, no markdown, no backticks, no explanation:

{
  "report_title": "string",
  "report_date": "ISO date",
  "opening_line": "string",
  "closing_line": "string",
  "sections": {
    "N": {
      "label": "Narrow · city name",
      "mood_line": "string",
      "stories": [
        {
          "article_id": "string",
          "headline": "string",
          "hook": "string",
          "summary": "string",
          "tone_label": "string",
          "url": "string",
          "source_name": "string",
          "source_icon": "string or null",
          "image_url": "string or null",
          "video_url": "string or null",
          "matched_tags": ["string"],
          "relevance_score": 0.0,
          "layer": "N",
          "category": ["string"],
          "published_at": "string"
        }
      ]
    },
    "E": { "label": "Expanded · country", "mood_line": "string", "stories": [] },
    "W": { "label": "Wide · continent", "mood_line": "string", "stories": [] },
    "S": { "label": "Sweeping · World", "mood_line": "string", "stories": [] }
  }
}

Never use: delve, crucial, groundbreaking, game-changer, it's worth noting, in conclusion, furthermore. Write like a sharp human editor. Summaries must never start with "This article discusses."
"""

# ---------------------------------------------------------------------------
# Pass 1 — lightweight triage: classify articles into layers + score them
# ---------------------------------------------------------------------------

_TRIAGE_PROMPT = """You are a geographic news article classifier for a personalized briefing engine.

Given a user location and a list of articles, assign each article:

layer — geographic relevance:
  N = specifically about the user's CITY (country matches user's country AND city name appears in title/description)
  E = about the user's COUNTRY (country matches, city not specifically mentioned)
  W = about the user's CONTINENT or an immediately neighbouring country
  S = global / other continents / Technology / AI / Cybersecurity / Science / Space (always S regardless of country)

score — relevance 0.0–1.0:
  +0.40 high-priority tag match
  +0.20 medium-priority tag match
  +0.10 low-priority tag match
  +0.10 if pubDate suggests published in last 12 hours
  +0.05 if image_url is present

Return ONLY compact valid JSON, no markdown, no explanation:
{"results": [{"id": "article_id", "layer": "S", "score": 0.45}, ...]}

Every input article must appear in results. Score 0.0 for articles you would normally drop.
"""


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


# Required fields for a story to render in the frontend. Anything missing one
# of these is dropped during sanitisation — better to lose a story than crash
# the layer tab. Array fields get defaulted to [] so list accesses don't blow up.
_STORY_REQUIRED = ("article_id", "headline", "url")
_STORY_ARRAY_DEFAULTS = ("matched_tags", "category")
_STORY_NULLABLE_DEFAULTS = {
    "hook": "",
    "summary": "",
    "tone_label": "INSIGHT",
    "source_name": "",
    "source_icon": None,
    "image_url": None,
    "video_url": None,
    "relevance_score": 0.3,
    "layer": "S",
    "published_at": "",
}


def _sanitize_report(data: dict) -> dict:
    """Drop partial stories and fill safe defaults so the frontend never crashes.

    The writer occasionally truncates near the end of the JSON; _safe_json_load
    closes the structure but the final story object can be missing arrays the UI
    indexes into (matched_tags[0], category, etc.). Filter and default here.
    """
    sections = data.get("sections") or {}
    cleaned_sections: dict = {}
    dropped_total = 0

    for layer_key, section in sections.items():
        if not isinstance(section, dict):
            continue
        raw_stories = section.get("stories") or []
        kept: list = []
        for s in raw_stories:
            if not isinstance(s, dict):
                dropped_total += 1
                continue
            # Hard requirements: id, headline, url. Without these the card is unusable.
            if not all(s.get(k) for k in _STORY_REQUIRED):
                dropped_total += 1
                continue
            for arr_key in _STORY_ARRAY_DEFAULTS:
                if not isinstance(s.get(arr_key), list):
                    s[arr_key] = []
            for k, default in _STORY_NULLABLE_DEFAULTS.items():
                if k not in s:
                    s[k] = default
            kept.append(s)

        cleaned_sections[layer_key] = {
            "label": section.get("label") or layer_key,
            "mood_line": section.get("mood_line") or "",
            "stories": kept,
        }

    if dropped_total:
        logger.warning("Sanitised report dropped %d partial/invalid stories", dropped_total)

    # Ensure all four layers exist so the frontend's tabs are stable.
    for layer_key in ("N", "E", "W", "S"):
        cleaned_sections.setdefault(layer_key, {"label": layer_key, "mood_line": "", "stories": []})

    data["sections"] = cleaned_sections
    return data


def triage_articles(user, stories: list[dict]) -> dict[str, dict]:
    """
    Pass 1 — classify articles into N/E/W/S layers and score them.
    Fast and cheap: sends only article_id, title, trimmed description, country, category.
    Returns {article_id: {layer, score}} or {} on failure (caller treats empty as unknown).
    """
    if not stories:
        return {}

    compact = [
        {
            "id": s["article_id"],
            "title": s["title"],
            "desc": (s.get("description") or "")[:150],
            "country": s.get("country"),
            "category": s.get("category") or [],
            "image_url": bool(s.get("image_url")),
            "pubDate": s.get("pubDate", ""),
        }
        for s in stories
    ]

    user_msg = json.dumps(
        {
            "user": {
                "city": user.city,
                "country": user.country,
                "continent": user.continent,
                "tags": user.tags or [],
            },
            "articles": compact,
        },
        ensure_ascii=False,
    )

    messages = [
        {"role": "system", "content": _TRIAGE_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.1,
            # 8K is deepseek-chat's max output; previously 4K, which truncated
            # whenever ~150+ articles came in (each result row is ~35 tokens).
            max_tokens=8192,
            # Enforces a parseable JSON object — eliminates mid-string truncation
            # from the model's side (it self-closes when nearing the cap).
            response_format={"type": "json_object"},
        )
        summary = _summarize_response(response, "triage")
        content = (response.choices[0].message.content or "").strip()
        if not content:
            # Common cause: rate-limit, content filter, or finish_reason=length
            # with no actual content generated. Triage is non-fatal — log loud
            # and return empty hints so the writer pass can still run.
            logger.warning(
                "Triage returned empty content — prompt=%s response=%s",
                _summarize_messages(messages), summary,
            )
            return {}
        data = _safe_json_load(content)
        return {
            r["id"]: {"layer": r.get("layer", "S"), "score": float(r.get("score", 0.3))}
            for r in (data.get("results") or [])
            if r.get("id")
        }
    except Exception as exc:
        # Triage failures are recoverable (the writer still runs without hints),
        # so we log a full diagnostic block but don't raise.
        logger.warning(
            "Triage failed (%s) — proceeding without hints. prompt=%s",
            exc, _summarize_messages(messages),
        )
        return {}


def generate_report(
    user,
    stories: list[dict],
    temperature: float = 0.7,
    max_stories: int = 15,
    triage_hints: dict[str, dict] | None = None,
    min_city: int = 10,
    min_country: int = 10,
    min_continent: int = 10,
    min_world: int = 30,
) -> tuple[dict, str]:
    # Inject triage hints into each article so DeepSeek can use pre-computed assignments
    articles_payload = []
    for s in stories:
        entry = dict(s)
        if triage_hints:
            hint = triage_hints.get(s.get("article_id", ""))
            if hint:
                entry["layer_hint"] = hint["layer"]
                entry["score_hint"] = hint["score"]
        articles_payload.append(entry)

    user_message = json.dumps({
        "generation_config": {
            "max_stories": max_stories,
            "min_city": min_city,
            "min_country": min_country,
            "min_continent": min_continent,
            "min_world": min_world,
        },
        "user_profile": {
            "city": user.city,
            "country": user.country,
            "continent": user.continent,
            "tags": user.tags or [],
            "blocked_words": user.blocked_words or [],
        },
        "articles": articles_payload,
    }, ensure_ascii=False)

    # We use deepseek-chat (not deepseek-reasoner): the reasoner burns its
    # completion budget on chain-of-thought before writing JSON, and on long
    # SYSTEM_PROMPT + 180-article payloads it routinely hits the 8K cap mid-CoT
    # with content_chars=0. deepseek-chat skips that step, supports JSON mode
    # (self-closes valid JSON when the cap approaches), and honours temperature.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        # Network / API errors before we even get a response — wrap with prompt
        # context so the failed job's error_message is actionable.
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
        # With json_object mode this should be rare — usually a content filter
        # trigger or a max_tokens=0 misconfiguration. Log everything we have.
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
        # JSON mode guarantees parseable output, but _safe_json_load also covers
        # the rare edge case where the cap clips a tail-end story field.
        parsed = _safe_json_load(raw)
        sanitised = _sanitize_report(parsed)
        return sanitised, raw
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
