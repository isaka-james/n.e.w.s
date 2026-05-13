import logging
import threading
import traceback
from datetime import date, datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session, select
from database import engine, get_session
from models import User, CachedStories, Report, GenerationJob
from auth import get_current_user
from fetcher import fetch_stories, fetch_local_boost
from deepseek import generate_report, triage_articles, DeepSeekError

router = APIRouter(prefix="/reports", tags=["reports"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress reporting — the frontend polls /reports/status and renders a
# percentage bar + stage label so users see what the engine is doing. Each
# milestone in the pipeline below bumps the job's stage and progress.
# ---------------------------------------------------------------------------

def _set_progress(job_id: str, stage: str, progress: int) -> None:
    """Update stage + progress for a running job. Safe to call from any thread."""
    with Session(engine) as s:
        job = s.get(GenerationJob, job_id)
        if not job or job.status != "running":
            return
        job.stage = stage
        job.progress = max(0, min(100, progress))
        job.updated_at = datetime.utcnow()
        s.add(job)
        s.commit()


# ---------------------------------------------------------------------------
# Background worker — runs in a separate thread so the POST returns instantly
# ---------------------------------------------------------------------------

def _run_generation(
    job_id: str,
    user_id: str,
    do_force: bool,
    fresh: bool,
    temperature: float,
    use_newsdata: bool,
    use_newsapi: bool,
    use_newscatcher: bool,
    use_gnews: bool,
    use_guardian: bool,
    use_nytimes: bool,
    target_city: int = 10,
    target_country: int = 10,
    target_continent: int = 10,
    target_world: int = 30,
):
    """Execute the full generation pipeline and update the job status in DB."""
    # Each background thread needs its own session
    with Session(engine) as session:
        job = session.get(GenerationJob, job_id)
        if not job:
            return

        user = session.get(User, user_id)
        if not user:
            job.status = "failed"
            job.error_message = "User not found"
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()
            return

        today = date.today()

        try:
            existing_report = session.exec(
                select(Report).where(
                    Report.user_id == user_id,
                    Report.report_date == today,
                )
            ).first()

            if existing_report and not do_force:
                # Already done — mark completed (fast path)
                job.status = "completed"
                job.stage = "completed"
                job.progress = 100
                job.updated_at = datetime.utcnow()
                session.add(job)
                session.commit()
                return

            if existing_report:
                session.delete(existing_report)
                session.commit()

            cached = session.exec(
                select(CachedStories).where(
                    CachedStories.user_id == user_id,
                    CachedStories.fetch_date == today,
                )
            ).first()

            if fresh and cached:
                session.delete(cached)
                session.commit()
                cached = None

            if cached:
                # Cached-story path: skip fetching entirely, just retriage + write.
                _set_progress(job_id, "reading_cache", 30)
                stories = cached.stories
                _set_progress(job_id, "triaging", 50)
                triage = triage_articles(user, stories)
                _set_progress(job_id, "writing", 65)

            else:
                # Fetch — each source completion bumps progress within 10–45 %.
                _set_progress(job_id, "fetching_news", 10)

                def _on_source_done(name: str, done: int, total: int) -> None:
                    # Map (1/N..N/N) → (10..45)
                    pct = 10 + int((done / max(1, total)) * 35)
                    _set_progress(job_id, "fetching_news", pct)

                stories = fetch_stories(
                    user,
                    use_newsdata=use_newsdata,
                    use_newsapi=use_newsapi,
                    use_newscatcher=use_newscatcher,
                    use_gnews=use_gnews,
                    use_guardian=use_guardian,
                    use_nytimes=use_nytimes,
                    on_source_done=_on_source_done,
                )
                if not stories:
                    raise RuntimeError("No stories returned from any news source")

                # ── Pass 1: AI triage ─────────────────────────────────────────
                _set_progress(job_id, "triaging", 48)
                triage = triage_articles(user, stories)
                _set_progress(job_id, "triaging", 55)

                # ── Pass 2: Gap-fill loop ─────────────────────────────────────
                # Only one round, only if a local layer is genuinely empty. We no
                # longer chase arbitrary "minimums" — the writer can't drop a
                # layer anymore, so as long as each layer has SOMETHING we move on.
                seen_ids: set[str] = {s["article_id"] for s in stories}
                n_count = sum(1 for h in triage.values() if h["layer"] == "N")
                e_count = sum(1 for h in triage.values() if h["layer"] == "E")

                if n_count == 0 or e_count == 0:
                    logger.info(
                        "Layer gap — N=%d E=%d; running one local boost for user %s",
                        n_count, e_count, user_id,
                    )
                    _set_progress(job_id, "gap_filling", 60)
                    extra = fetch_local_boost(user, seen_ids)
                    if extra:
                        stories.extend(extra)
                        triage.update(triage_articles(user, extra))

                # Hard cap — keep payload manageable
                stories = stories[:180]

                session.add(CachedStories(
                    user_id=user_id,
                    fetch_date=today,
                    stories=stories,
                ))
                session.commit()
                _set_progress(job_id, "writing", 65)

            # ── Pass 3: Bucket in Python, then write ─────────────────────────
            report_data, raw_response = generate_report(
                user, stories,
                temperature=temperature,
                triage_hints=triage,
                targets={
                    "N": target_city,
                    "E": target_country,
                    "W": target_continent,
                    "S": target_world,
                },
            )

            report = Report(
                user_id=user_id,
                report_date=today,
                report_title=report_data.get("report_title", "Today's Briefing"),
                opening_line=report_data.get("opening_line", ""),
                closing_line=report_data.get("closing_line", ""),
                sections=report_data.get("sections", {}),
                raw_response=raw_response,
            )
            _set_progress(job_id, "finalizing", 97)
            session.add(report)

            # Re-read the job since _set_progress may have updated it via another session
            session.refresh(job)
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()

        except Exception as exc:
            # Log the FULL stack trace so the operator can chase the cause from
            # `docker logs news-backend-1` without rerunning.
            logger.exception(
                "Generation job %s failed for user %s at stage=%s progress=%s",
                job_id, user_id, getattr(job, "stage", "?"), getattr(job, "progress", "?"),
            )

            # Build a UI-friendly error message. For DeepSeekError we expose the
            # structured context dict; for everything else we tag the exception
            # class so the message itself is searchable.
            if isinstance(exc, DeepSeekError):
                ui_msg = f"{exc.label}: {exc.reason}"
                if exc.context:
                    # Compact one-line context — only the parts likely to fit
                    # in a notification UI without overwhelming it.
                    bits = ", ".join(
                        f"{k}={v}" for k, v in exc.context.items()
                        if k in {"finish_reason", "completion_tokens", "reasoning_tokens", "prompt_tokens"}
                    )
                    if bits:
                        ui_msg = f"{ui_msg} ({bits})"
            else:
                ui_msg = f"{exc.__class__.__name__}: {exc}"
                # Tack on the last 3 frames of the traceback so a stuck job is
                # actually debuggable from the Activity panel alone.
                tail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                last_frames = "\n".join(tail.strip().splitlines()[-6:])
                ui_msg = f"{ui_msg}\n{last_frames}"

            session.refresh(job)
            job.status = "failed"
            job.error_message = ui_msg
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/generate")
def generate(
    force: bool = Query(default=False, description="Re-run AI using today's cached stories"),
    fresh: bool = Query(default=False, description="Re-fetch news AND re-run AI (implies force)"),
    temperature: float = Query(default=0.7, ge=0.1, le=1.5),
    use_newsdata: bool = Query(default=True),
    use_newsapi: bool = Query(default=True),
    use_newscatcher: bool = Query(default=True),
    use_gnews: bool = Query(default=True),
    use_guardian: bool = Query(default=True),
    use_nytimes: bool = Query(default=True),
    # Per-layer story target. Each layer is independently capped at this many.
    # Names kept as min_* for frontend backwards-compat; they now act as targets.
    min_city: int = Query(default=8, ge=0, le=30),
    min_country: int = Query(default=8, ge=0, le=30),
    min_continent: int = Query(default=8, ge=0, le=30),
    min_world: int = Query(default=12, ge=0, le=40),
    # "generate" | "ai-only" | "from-scratch" — used for display only
    job_type: str = Query(default="generate"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    today = date.today()
    do_force = force or fresh

    # If report already exists and no override, return it immediately (no job needed)
    existing_report = session.exec(
        select(Report).where(
            Report.user_id == current_user.id,
            Report.report_date == today,
        )
    ).first()
    if existing_report and not do_force:
        return {
            "job_id": None,
            "status": "completed",
            "report": {
                "report_title": existing_report.report_title,
                "opening_line": existing_report.opening_line,
                "closing_line": existing_report.closing_line,
                "sections": existing_report.sections,
                "report_date": existing_report.report_date.isoformat(),
                "cached": True,
            },
        }

    # Cancel any previous running job for this user (stale)
    stale_jobs = session.exec(
        select(GenerationJob).where(
            GenerationJob.user_id == current_user.id,
            GenerationJob.status == "running",
        )
    ).all()
    for stale in stale_jobs:
        stale.status = "failed"
        stale.error_message = "Superseded by a new generation request"
        stale.updated_at = datetime.utcnow()
        session.add(stale)

    job = GenerationJob(
        user_id=current_user.id,
        type=job_type,
        status="running",
        options={
            "force": do_force,
            "fresh": fresh,
            "temperature": temperature,
            "use_newsdata": use_newsdata,
            "use_newsapi": use_newsapi,
            "use_newscatcher": use_newscatcher,
            "use_gnews": use_gnews,
            "use_guardian": use_guardian,
            "use_nytimes": use_nytimes,
            "target_city": min_city,
            "target_country": min_country,
            "target_continent": min_continent,
            "target_world": min_world,
        },
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Spawn background thread — the session is committed so the thread can read the job
    thread = threading.Thread(
        target=_run_generation,
        kwargs=dict(
            job_id=job.id,
            user_id=current_user.id,
            do_force=do_force,
            fresh=fresh,
            temperature=temperature,
            use_newsdata=use_newsdata,
            use_newsapi=use_newsapi,
            use_newscatcher=use_newscatcher,
            use_gnews=use_gnews,
            use_guardian=use_guardian,
            use_nytimes=use_nytimes,
            target_city=min_city,
            target_country=min_country,
            target_continent=min_continent,
            target_world=min_world,
        ),
        daemon=True,
    )
    thread.start()

    return {"job_id": job.id, "status": "running", "report": None}


@router.get("/status")
def get_status(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Returns the latest generation job for the authenticated user.
    If a job is running, the frontend should keep polling.
    If completed/failed with no job_id stored, returns None.
    """
    job = session.exec(
        select(GenerationJob)
        .where(GenerationJob.user_id == current_user.id)
        .order_by(GenerationJob.created_at.desc())  # type: ignore[arg-type]
    ).first()

    if not job:
        return None

    return {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Auto-generation helper — called by the scheduler in main.py
# ---------------------------------------------------------------------------

def schedule_auto_generation(user_id: str) -> None:
    """
    Create a GenerationJob and spawn a background thread for a user.
    Safe to call concurrently; guards against duplicate jobs and existing reports.
    """
    today = date.today()
    with Session(engine) as session:
        # Skip if report already exists for today
        existing = session.exec(
            select(Report).where(Report.user_id == user_id, Report.report_date == today)
        ).first()
        if existing:
            return

        # Skip if a job is already running
        running = session.exec(
            select(GenerationJob).where(
                GenerationJob.user_id == user_id,
                GenerationJob.status == "running",
            )
        ).first()
        if running:
            return

        job = GenerationJob(
            user_id=user_id,
            type="auto",
            status="running",
            options={
                "auto": True,
                "fresh": True,
                "temperature": 0.7,
                "use_newsdata": True,
                "use_newsapi": True,
                "use_newscatcher": True,
                "use_gnews": True,
                "use_guardian": True,
                "use_nytimes": True,
            },
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    threading.Thread(
        target=_run_generation,
        kwargs=dict(
            job_id=job_id,
            user_id=user_id,
            do_force=False,
            fresh=True,
            temperature=0.7,
            use_newsdata=True,
            use_newsapi=True,
            use_newscatcher=True,
            use_gnews=True,
            use_guardian=True,
            use_nytimes=True,
            target_city=8,
            target_country=8,
            target_continent=8,
            target_world=12,
        ),
        daemon=True,
    ).start()


@router.get("/today")
def get_today(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    today = date.today()
    report = session.exec(
        select(Report).where(
            Report.user_id == current_user.id,
            Report.report_date == today,
        )
    ).first()

    if not report:
        return None

    return {
        "report_title": report.report_title,
        "opening_line": report.opening_line,
        "closing_line": report.closing_line,
        "sections": report.sections,
        "report_date": report.report_date.isoformat(),
        "cached": True,
    }

