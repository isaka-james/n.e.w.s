"""
NewsCatcher CatchAll API fetcher — https://catchall.newscatcherapi.com

CatchAll is an async, recall-first web search API:
  submit → analyzing → fetching → clustering → enriching → completed (10–15 min)

Free plan constraints:
  • 1 concurrent job across the API key
  • 100 records max per search
  • 2-week lookback window
  • lite or base modes (no Deep)
  • Pay-as-you-go credits (lite = 100 flat / search, base = 10 / record)

Strategy:
  Because the pipeline is slow (10–15 min) and only 1 job runs at a time, we
  cannot inline-wait during report generation. Instead:

    1. Reuse: if a completed CatchAll job exists for this user in the last 25h,
       use its cached records (no API call).
    2. Resume: if one is running/enriching, poll briefly (~60s). If it finishes
       within that budget, use it; otherwise return what's available.
    3. Submit: if none exists and no other CatchAll job is running globally,
       submit a new `lite` job and poll briefly. Persist the job_id so the next
       generation (or the background poller) picks it up when ready.

  A background poller in main.py advances pending jobs every couple of minutes
  so subsequent generations the same day pull cached results instantly.

Citations from each event cluster are flattened into article-shaped records
matching the rest of the fetcher pipeline.
"""
import hashlib
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import text
from sqlmodel import Session, select

from config import settings
from database import engine
from models import CatchAllJob

logger = logging.getLogger(__name__)

CATCHALL_BASE = "https://catchall.newscatcherapi.com"
CATCHALL_SUBMIT     = f"{CATCHALL_BASE}/catchAll/submit"
CATCHALL_STATUS_FMT = f"{CATCHALL_BASE}/catchAll/status/{{job_id}}"
CATCHALL_PULL_FMT   = f"{CATCHALL_BASE}/catchAll/pull/{{job_id}}"

# Free-plan ceilings
FREE_PLAN_LIMIT = 100         # max records per search
FREE_PLAN_LOOKBACK_DAYS = 12  # 14 max — kept as a safety cap

# Discovery window: pages discovered in the last N days. A tight 1-day window
# makes CatchAll finish in under 2 min (often in seconds) instead of the
# default 5-day window's 10–15 min. This is the single biggest perf lever.
DISCOVERY_WINDOW_DAYS = 1

# Inline poll budget — sized so a 1-day-window job typically completes within it.
INLINE_POLL_SECONDS = 180
INLINE_POLL_INTERVAL = 3

# A completed job is reusable for this many hours before we submit a fresh one.
# Reports are daily, so 23h means at most one CatchAll job per user per day.
JOB_REUSE_HOURS = 23

# A "running" job older than this is treated as stale — the CatchAll pipeline
# normally finishes in <2 min with a 1-day window, so an hour+ old job is dead.
STALE_RUNNING_HOURS = 1

# Pipeline statuses that mean "still working — keep polling"
RUNNING_STATUSES = {"submitted", "analyzing", "fetching", "clustering", "enriching"}
TERMINAL_STATUSES = {"completed", "failed"}


def _headers() -> dict[str, str]:
    return {
        "x-api-key": settings.NEWSCATCHER_API_KEY,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Rate limiter — CatchAll caps status checks at 3 req/s per API key. Across our
# 4 uvicorn workers + inline poll + sweeper this is easy to breach, so we
# throttle every outgoing CatchAll HTTP call to ~2.5 req/s per worker.
# ---------------------------------------------------------------------------
_throttle_lock = threading.Lock()
_throttle_last_call_at = 0.0
_THROTTLE_MIN_INTERVAL = 0.4  # seconds between calls (≈2.5 req/s per worker)


def _throttle() -> None:
    """Block until at least _THROTTLE_MIN_INTERVAL has elapsed since the last call."""
    global _throttle_last_call_at
    with _throttle_lock:
        delta = time.monotonic() - _throttle_last_call_at
        if delta < _THROTTLE_MIN_INTERVAL:
            time.sleep(_THROTTLE_MIN_INTERVAL - delta)
        _throttle_last_call_at = time.monotonic()


# ---------------------------------------------------------------------------
# Cross-worker sweeper lock — uvicorn --workers 4 means each worker spawns its
# own _catchall_sweeper daemon. Without coordination they'd all hit /status
# simultaneously and trip the 3 req/s ceiling. Postgres advisory locks let
# exactly one worker hold the sweeper token at a time; the rest skip.
# ---------------------------------------------------------------------------
SWEEPER_LOCK_KEY = 8172639  # arbitrary 32-bit int unique to this app


def _acquire_sweeper_lock(conn) -> bool:
    """Try to grab the cross-worker sweeper lock. Returns True if we got it."""
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SWEEPER_LOCK_KEY}).scalar())


def _release_sweeper_lock(conn) -> None:
    try:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SWEEPER_LOCK_KEY})
    except Exception:
        pass


def _now() -> datetime:
    return datetime.utcnow()


def _source_from_url(url: str) -> str:
    """Derive a publication name from a citation URL host (e.g. www.example.com → example.com)."""
    try:
        host = urlparse(url).netloc or ""
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _article_id(link: str) -> str:
    return "nc_" + hashlib.md5(link.encode()).hexdigest()


def _build_query(user) -> str:
    """Compose a natural-language CatchAll query covering the user's interests."""
    tag_names = [t.get("name") for t in (user.tags or []) if t.get("name")]
    high_med = [t.get("name") for t in (user.tags or []) if t.get("priority") in ("high", "medium") and t.get("name")]
    topics = high_med or tag_names
    parts: list[str] = []
    parts.append(f"Recent news and events in {user.city}, {user.country}")
    if user.continent:
        parts.append(f"or across {user.continent}")
    if topics:
        topic_str = ", ".join(topics[:8])
        parts.append(f"covering topics like {topic_str}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# HTTP wrappers — never raise; return None / [] on failure
# ---------------------------------------------------------------------------

def _iso8601_z(dt: datetime) -> str:
    """Format a UTC datetime as ISO 8601 with Z suffix (CatchAll requires UTC)."""
    return dt.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%SZ")


def _post_submit(query: str, mode: str = "lite") -> str | None:
    """Submit a new CatchAll job. Returns its job_id or None on failure.

    We pin a tight 1-day discovery window — CatchAll only scans pages indexed
    in the last 24h, finishing the whole pipeline in under 2 min (sometimes
    seconds) rather than the 10–15 min the default 5-day window takes.
    """
    end = datetime.utcnow()
    start = end - timedelta(days=DISCOVERY_WINDOW_DAYS)
    body = {
        "query": query,
        "limit": FREE_PLAN_LIMIT,
        "mode": mode,
        "start_date": _iso8601_z(start),
        "end_date": _iso8601_z(end),
    }
    try:
        _throttle()
        resp = httpx.post(CATCHALL_SUBMIT, json=body, headers=_headers(), timeout=30)
        if resp.status_code >= 400:
            logger.warning("CatchAll submit %s: %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        return data.get("job_id")
    except Exception as exc:
        logger.warning("CatchAll submit failed: %s", exc)
        return None


def _get_status(job_id: str) -> str | None:
    """Returns the CatchAll pipeline status, or None on network failure."""
    try:
        _throttle()
        resp = httpx.get(CATCHALL_STATUS_FMT.format(job_id=job_id), headers=_headers(), timeout=15)
        if resp.status_code >= 400:
            logger.warning("CatchAll status %s for %s: %s", resp.status_code, job_id, resp.text[:200])
            return None
        return (resp.json() or {}).get("status")
    except Exception as exc:
        logger.warning("CatchAll status failed for %s: %s", job_id, exc)
        return None


def _get_pull(job_id: str) -> dict | None:
    """Pull all results (paginated until exhausted) and return the merged payload."""
    try:
        _throttle()
        resp = httpx.get(
            CATCHALL_PULL_FMT.format(job_id=job_id),
            headers=_headers(),
            params={"page": 1, "page_size": 100},
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning("CatchAll pull %s for %s: %s", resp.status_code, job_id, resp.text[:200])
            return None
        data = resp.json() or {}
        all_records = list(data.get("all_records") or [])
        total_pages = int(data.get("total_pages") or 1)
        # Pull remaining pages if any
        for page in range(2, total_pages + 1):
            try:
                _throttle()
                page_resp = httpx.get(
                    CATCHALL_PULL_FMT.format(job_id=job_id),
                    headers=_headers(),
                    params={"page": page, "page_size": 100},
                    timeout=30,
                )
                if page_resp.status_code >= 400:
                    break
                page_data = page_resp.json() or {}
                all_records.extend(page_data.get("all_records") or [])
            except Exception as exc:
                logger.warning("CatchAll pull page %d failed for %s: %s", page, job_id, exc)
                break
        data["all_records"] = all_records
        return data
    except Exception as exc:
        logger.warning("CatchAll pull failed for %s: %s", job_id, exc)
        return None


# ---------------------------------------------------------------------------
# Record flattening
# ---------------------------------------------------------------------------

def _flatten_records(pull_data: dict, fallback_country: str | None) -> list[dict]:
    """Turn CatchAll event clusters into article-shaped records.

    Each cluster has N citations (source web pages). We emit one article per
    citation; the cluster's record_title is used as the description so DeepSeek
    has the event summary as context.
    """
    out: list[dict] = []
    records = pull_data.get("all_records") or []
    for rec in records:
        event_title = (rec.get("record_title") or "").strip()
        enrichment = rec.get("enrichment") or {}
        confidence = enrichment.get("enrichment_confidence")  # "high"/"medium"/"low"
        # Drop low-confidence clusters — they tend to be noisy or wrong
        if confidence == "low":
            continue

        citations = rec.get("citations") or []
        for cit in citations:
            link = (cit.get("link") or "").strip()
            if not link:
                continue
            title = (cit.get("title") or event_title).strip()
            if not title:
                continue
            out.append({
                "article_id": _article_id(link),
                "title": title,
                # Use the cluster's headline as a short description — gives the AI
                # cross-citation context (e.g. multiple outlets covering same event).
                "description": event_title if event_title and event_title != title else "",
                "link": link,
                "image_url": None,
                "video_url": None,
                "source_name": _source_from_url(link),
                "source_icon": None,
                "country": fallback_country,
                "category": [],
                "keywords": [],
                "pubDate": cit.get("published_date") or "",
                "language": "en",
            })
    return out


# ---------------------------------------------------------------------------
# DB helpers — every operation uses its own short-lived session
# ---------------------------------------------------------------------------

def _latest_user_job(user_id: str) -> CatchAllJob | None:
    """Most recent CatchAll job for a user, if any."""
    with Session(engine) as s:
        return s.exec(
            select(CatchAllJob)
            .where(CatchAllJob.user_id == user_id)
            .order_by(CatchAllJob.created_at.desc())  # type: ignore[arg-type]
        ).first()


def _any_job_in_flight() -> bool:
    """True if any user's CatchAll job is still running (free-plan concurrency = 1).

    We only block on jobs created in the last 30 minutes — anything older was
    probably abandoned (CatchAll completes within 15 min in practice).
    """
    cutoff = _now() - timedelta(minutes=30)
    with Session(engine) as s:
        running = s.exec(
            select(CatchAllJob)
            .where(CatchAllJob.status.in_(list(RUNNING_STATUSES)))  # type: ignore[union-attr]
            .where(CatchAllJob.created_at >= cutoff)
        ).first()
    return running is not None


def _update_job(job_pk: str, *, status: str | None = None,
                records: list[dict] | None = None,
                error_message: str | None = None) -> None:
    with Session(engine) as s:
        job = s.get(CatchAllJob, job_pk)
        if not job:
            return
        if status is not None:
            job.status = status
        if records is not None:
            job.records = records
        if error_message is not None:
            job.error_message = error_message
        job.updated_at = _now()
        s.add(job)
        s.commit()


def _create_job(user_id: str, job_id: str, query: str, mode: str) -> str:
    with Session(engine) as s:
        rec = CatchAllJob(
            user_id=user_id,
            job_id=job_id,
            status="submitted",
            query=query,
            mode=mode,
        )
        s.add(rec)
        s.commit()
        s.refresh(rec)
        return rec.id


# ---------------------------------------------------------------------------
# Job advance: poll + pull when ready. Called both inline and by the poller.
# ---------------------------------------------------------------------------

def advance_catchall_job(
    job_pk: str,
    *,
    fallback_country: str | None,
    max_seconds: float = 0,
) -> list[dict]:
    """Advance a single CatchAll job toward completion.

    If `max_seconds > 0`, keep polling (every INLINE_POLL_INTERVAL s) until done
    or the budget runs out. Returns any records that are currently available
    (empty list if the job hasn't reached `enriching` yet).
    """
    with Session(engine) as s:
        job = s.get(CatchAllJob, job_pk)
        if not job:
            return []
        if job.status == "completed":
            return job.records or []
        if job.status == "failed":
            return []
        catchall_job_id = job.job_id

    deadline = time.monotonic() + max_seconds

    while True:
        status = _get_status(catchall_job_id)
        if status is None:
            # Network blip — back off; record stays as-is for next attempt.
            return []

        if status in TERMINAL_STATUSES:
            if status == "failed":
                _update_job(job_pk, status="failed", error_message="CatchAll pipeline reported failed")
                return []
            # completed — pull and persist
            pull = _get_pull(catchall_job_id)
            if pull is None:
                return []
            records = _flatten_records(pull, fallback_country=fallback_country)
            _update_job(job_pk, status="completed", records=records)
            return records

        # Still running. enriching means partial results are available.
        if status == "enriching":
            pull = _get_pull(catchall_job_id)
            if pull is not None:
                partial = _flatten_records(pull, fallback_country=fallback_country)
                # Persist the partial so a later call sees progress even if we time out.
                _update_job(job_pk, status=status, records=partial)
            else:
                _update_job(job_pk, status=status)
        else:
            _update_job(job_pk, status=status)

        if time.monotonic() >= deadline:
            with Session(engine) as s:
                job = s.get(CatchAllJob, job_pk)
                return (job.records if job else []) or []

        time.sleep(INLINE_POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Background sweeper — poll all in-flight jobs once.
# ---------------------------------------------------------------------------

def sweep_pending_catchall_jobs() -> None:
    """Advance every in-flight CatchAll job by one status check.

    Designed to be called periodically from a daemon thread. With uvicorn running
    multiple workers, only one worker holds the cross-process advisory lock at
    any time; others skip. This keeps us well under CatchAll's 3 req/s ceiling.
    """
    with engine.connect() as conn:
        if not _acquire_sweeper_lock(conn):
            return  # another worker is sweeping
        try:
            with Session(engine) as s:
                pending = s.exec(
                    select(CatchAllJob).where(CatchAllJob.status.in_(list(RUNNING_STATUSES)))  # type: ignore[union-attr]
                ).all()

            for job in pending:
                # Each call does at most one status check + (if done) one pull,
                # and _throttle() spaces them out within the 3 req/s ceiling.
                advance_catchall_job(job.id, fallback_country=None, max_seconds=0)
        finally:
            _release_sweeper_lock(conn)


# ---------------------------------------------------------------------------
# Public entrypoint used by fetcher.py
# ---------------------------------------------------------------------------

def fetch_newscatcher_stories(user) -> list[dict]:
    """Get NewsCatcher CatchAll records for this user, prioritising cached results.

    Returns an empty list if no completed job is available and a freshly-submitted
    one hasn't finished within the inline poll budget. The next generation (or the
    background sweeper) will pick up the results when ready.
    """
    if not settings.NEWSCATCHER_API_KEY:
        return []

    latest = _latest_user_job(user.id)
    latest_age_hours = (
        (_now() - latest.created_at).total_seconds() / 3600 if latest else None
    )

    # 1. Reuse a recent completed job's records — no API call needed.
    if (
        latest
        and latest.status == "completed"
        and latest_age_hours is not None
        and latest_age_hours <= JOB_REUSE_HOURS
    ):
        return list(latest.records or [])

    # 2. Resume a still-running job for this user — poll briefly. Skip if the
    #    job is stale (CatchAll likely abandoned it).
    if (
        latest
        and latest.status in RUNNING_STATUSES
        and latest_age_hours is not None
        and latest_age_hours <= STALE_RUNNING_HOURS
    ):
        return advance_catchall_job(
            latest.id,
            fallback_country=user.country,
            max_seconds=INLINE_POLL_SECONDS,
        )

    # Mark a stale "running" job as failed so it stops blocking future submits.
    if (
        latest
        and latest.status in RUNNING_STATUSES
        and latest_age_hours is not None
        and latest_age_hours > STALE_RUNNING_HOURS
    ):
        _update_job(latest.id, status="failed", error_message="Stale — exceeded inline window")

    # 3. Submit a new job — but only if no other CatchAll job is in flight globally.
    if _any_job_in_flight():
        logger.info("CatchAll: another job already in flight, skipping submit for user %s", user.id)
        return []

    query = _build_query(user)
    catchall_job_id = _post_submit(query, mode="lite")
    if not catchall_job_id:
        return []

    job_pk = _create_job(user.id, catchall_job_id, query=query, mode="lite")
    return advance_catchall_job(
        job_pk,
        fallback_country=user.country,
        max_seconds=INLINE_POLL_SECONDS,
    )
