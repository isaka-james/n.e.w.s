import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from routers import auth_router, reports_router, users_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto-generation scheduler
# ---------------------------------------------------------------------------

def _run_auto_generate_check(*, catch_up: bool = False) -> None:
    """
    Check all users with auto_generate_time set.

    In normal mode (catch_up=False): only fire for users whose configured
    HH:MM matches the current UTC minute exactly.

    In catch-up mode (catch_up=True, called once on startup): also fire for
    users whose configured time has already passed today so a server restart
    never silently skips their morning generation.
    """
    from sqlmodel import Session, select
    from database import engine
    from models import User
    from routers.reports_router import schedule_auto_generation

    try:
        now = datetime.now(timezone.utc)
        current_hhmm = now.strftime("%H:%M")
        now_minutes = now.hour * 60 + now.minute

        with Session(engine) as session:
            users = session.exec(
                select(User).where(User.auto_generate_time.isnot(None))  # type: ignore[union-attr]
            ).all()

        for user in users:
            if not user.auto_generate_time:
                continue
            h, m = map(int, user.auto_generate_time.split(":"))
            configured_minutes = h * 60 + m

            should_fire = (
                user.auto_generate_time == current_hhmm
                or (catch_up and configured_minutes <= now_minutes)
            )
            if should_fire:
                schedule_auto_generation(user.id)

    except Exception as exc:
        logger.warning("Auto-generation check error: %s", exc)


def _scheduler_worker() -> None:
    """Daemon thread: fires every 60 s, aligned to the next full minute."""
    # Align to the next clock minute so the first check happens right on a minute boundary
    now = time.time()
    time.sleep(60 - (now % 60))

    while True:
        _run_auto_generate_check(catch_up=False)
        # Sleep until the next minute boundary
        now = time.time()
        time.sleep(60 - (now % 60))


def _catchall_sweeper() -> None:
    """Daemon thread: advance any in-flight CatchAll jobs every 30 seconds.

    With a 1-day discovery window CatchAll jobs typically finish in under 2 min,
    so a 30 s sweep catches completions quickly. Between generations the sweeper
    pulls completed jobs into the DB so the next user-triggered fetch is instant.
    Each sweep is one status check (no submit), well within free-plan limits.
    """
    from newscatcher_fetcher import sweep_pending_catchall_jobs

    # Stagger first run by 30 s so startup isn't all happening at once
    time.sleep(30)
    while True:
        try:
            sweep_pending_catchall_jobs()
        except Exception as exc:
            logger.warning("CatchAll sweep error: %s", exc)
        time.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()

    # One-time catch-up: fire for users whose auto-gen time already passed today
    threading.Thread(target=_run_auto_generate_check, kwargs={"catch_up": True}, daemon=True).start()

    # Ongoing minute-granularity scheduler
    threading.Thread(target=_scheduler_worker, daemon=True).start()

    # CatchAll sweeper: keeps async NewsCatcher jobs advancing between generations
    threading.Thread(target=_catchall_sweeper, daemon=True).start()

    yield


app = FastAPI(title="N.E.W.S. API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:4291"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "N.E.W.S. API"}


app.include_router(auth_router.router)
app.include_router(reports_router.router)
app.include_router(users_router.router)
