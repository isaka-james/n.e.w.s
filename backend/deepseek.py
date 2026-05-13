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

SYSTEM_PROMPT = """You are a news briefing writer. You receive a user profile and a set of articles ALREADY bucketed into four geographic layers (N, E, W, S). Your only job is to rewrite each article as a short editorial card and add prose around the report.

You do NOT filter, drop, merge, re-rank, or re-classify articles. Every article you receive must appear in its assigned layer in the output, in the same order. Bucketing is handled upstream.

Each article has a title and a short description snippet (not the full article). Base your rewrites ONLY on what the title and description actually say. Do not invent details.

For each article, write:
- headline: rewritten from the original title — punchy, clear, no clickbait
- hook: one sentence that creates interest
- summary: 1-2 sentences based ONLY on the title and description. If the description is thin, keep it short.
- tone_label: ONE of: BREAKING, VIRAL, ANALYSIS, SIGNAL, INSIGHT, LIGHTHEARTED

Tones:
- BREAKING — happening right now, fast-moving
- VIRAL — spreading fast, buzzy, high social interest
- ANALYSIS — expert opinion, deep reporting, investigation
- SIGNAL — early sign of a bigger trend
- INSIGHT — teaches something genuinely new
- LIGHTHEARTED — actually funny or heartwarming (only when it truly is)

For the report itself, write:
- report_title: creative, specific to today's news mood, never generic
- opening_line: 2-3 sentences, sharp and conversational, written to the reader without using their name. Never say "Here is your daily briefing."
- closing_line: 1-2 sentences, reflective or observational, never preachy
- For each layer, a mood_line: ONE punchy sentence. If the layer's stories array is empty, set mood_line to "Nothing notable here today."

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
          "tone_label": "string"
        }
      ]
    },
    "E": { "label": "Expanded · country", "mood_line": "string", "stories": [...] },
    "W": { "label": "Wide · continent", "mood_line": "string", "stories": [...] },
    "S": { "label": "Sweeping · World", "mood_line": "string", "stories": [...] }
  }
}

The stories array for each layer MUST contain exactly the same number of entries as the input layer, in the same order, with the same article_id values. Do not add, remove, or reorder articles.

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


# ---------------------------------------------------------------------------
# Deterministic bucketing — runs in Python after triage, before the writer.
# ---------------------------------------------------------------------------

_VALID_LAYERS = ("N", "E", "W", "S")


def _matched_tags(story: dict, user_tags: list[dict]) -> list[str]:
    """Return the user's tags whose name appears in the article's title/desc/keywords/category.

    Used both for matched_tags display and as a sanity check that we don't
    keep articles unconnected to the user's interests. Case-insensitive.
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


def _is_blocked(story: dict, blocked_words: list[str]) -> bool:
    """True if any blocked word appears in title or description (case-insensitive)."""
    if not blocked_words:
        return False
    haystack = (story.get("title") or "" + " " + (story.get("description") or "")).lower()
    return any(w.lower() in haystack for w in blocked_words if w)


def bucket_stories(
    user,
    stories: list[dict],
    triage_hints: dict[str, dict],
    targets: dict[str, int],
) -> dict[str, list[dict]]:
    """Group stories into N/E/W/S using triage hints, drop blocked words, take top-K per layer.

    The output is keyed by layer and each story is enriched with `matched_tags`
    and `relevance_score` so the writer doesn't need to re-derive them. Layers
    that have no candidates simply come back empty — no AI guessing involved.

    `targets` is a dict like {"N": 10, "E": 10, "W": 10, "S": 30} — the per-layer
    cap. Each layer gets up to that many stories, sorted by score desc.
    """
    blocked = user.blocked_words or []
    user_tags = user.tags or []

    buckets: dict[str, list[dict]] = {k: [] for k in _VALID_LAYERS}

    for s in stories:
        if _is_blocked(s, blocked):
            continue

        article_id = s.get("article_id") or ""
        hint = triage_hints.get(article_id) if triage_hints else None
        layer = (hint or {}).get("layer", "S")
        if layer not in _VALID_LAYERS:
            layer = "S"

        score = float((hint or {}).get("score", 0.3))

        # Drop low-relevance, unrelated articles only at very low scores. Anything
        # the triage pass thought was worth assigning a layer stays in the pool.
        if score < 0.15:
            continue

        enriched = dict(s)
        enriched["matched_tags"] = _matched_tags(s, user_tags)
        enriched["relevance_score"] = round(score, 3)
        enriched["layer"] = layer
        buckets[layer].append(enriched)

    # Sort each layer by score desc and cap at the per-layer target. This is the
    # cap that USED to fight with max_stories in the writer prompt — now it's
    # deterministic and the writer never sees more than this.
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


def _writer_payload(user, buckets: dict[str, list[dict]]) -> dict:
    """Build the compact per-layer payload sent to the writer.

    Only the fields the writer needs for rewriting prose — the deterministic
    passthrough fields (url, source_name, image_url, etc.) are NOT sent and
    are merged back from `buckets` after the response.
    """
    sections = {}
    for layer in _VALID_LAYERS:
        sections[layer] = {
            "label": _layer_label(layer, user),
            "stories": [
                {
                    "article_id": s["article_id"],
                    "title": s.get("title", ""),
                    "description": (s.get("description") or "")[:400],
                    "matched_tags": s.get("matched_tags", []),
                }
                for s in buckets.get(layer, [])
            ],
        }
    return {
        "user_profile": {
            "city": user.city,
            "country": user.country,
            "continent": user.continent,
        },
        "sections": sections,
    }


def _merge_writer_output(
    user,
    buckets: dict[str, list[dict]],
    writer: dict,
) -> dict:
    """Combine the writer's prose with the deterministic passthrough fields.

    The writer is asked to emit one entry per input story in the same order.
    We match by article_id with fallback to position, so a single missing or
    re-ordered entry can't drop the rest of the layer.
    """
    out_sections: dict[str, dict] = {}
    writer_sections = writer.get("sections") or {}

    for layer in _VALID_LAYERS:
        layer_stories = buckets.get(layer, [])
        writer_section = writer_sections.get(layer) or {}
        writer_stories = writer_section.get("stories") or []
        by_id = {ws.get("article_id"): ws for ws in writer_stories if ws.get("article_id")}

        out_stories: list[dict] = []
        for idx, source in enumerate(layer_stories):
            prose = by_id.get(source["article_id"]) or (
                writer_stories[idx] if idx < len(writer_stories) else {}
            )
            out_stories.append({
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
            })

        out_sections[layer] = {
            "label": _layer_label(layer, user),
            "mood_line": writer_section.get("mood_line") or (
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


def generate_report(
    user,
    stories: list[dict],
    temperature: float = 0.7,
    triage_hints: dict[str, dict] | None = None,
    targets: dict[str, int] | None = None,
) -> tuple[dict, str]:
    """Bucket stories deterministically, then ask DeepSeek to write prose.

    All filtering, classification, and per-layer capping happen in Python — the
    writer can no longer accidentally drop a whole layer. The writer's job is
    only to rewrite headlines, write hooks/summaries, pick a tone, and produce
    the report-level prose (title, opening, closing, mood lines).
    """
    targets = targets or {"N": 10, "E": 10, "W": 10, "S": 30}
    buckets = bucket_stories(user, stories, triage_hints or {}, targets)

    # If literally every layer is empty there's nothing to write. Return a
    # structurally-valid empty report so the UI still renders.
    if not any(buckets.values()):
        return {
            "report_title": "A quiet day on the wire.",
            "opening_line": "Nothing crossed the wire today that matches your filters.",
            "closing_line": "Check back tomorrow.",
            "sections": {layer: _empty_section(layer, user) for layer in _VALID_LAYERS},
        }, ""

    user_message = json.dumps(_writer_payload(user, buckets), ensure_ascii=False)

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
