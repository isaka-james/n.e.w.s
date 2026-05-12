from datetime import datetime, date
from typing import Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON, Text
import uuid


def uuid_str():
    return str(uuid.uuid4())


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=uuid_str, primary_key=True)
    email: str = Field(unique=True, index=True)
    name: str
    password_hash: str
    city: str
    country: str
    continent: str
    tags: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    blocked_words: list[str] = Field(default=[], sa_column=Column(JSON))
    # "HH:MM" in UTC (e.g. "07:00"), or None to disable auto-generation
    auto_generate_time: str | None = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CachedStories(SQLModel, table=True):
    __tablename__ = "cached_stories"

    id: str = Field(default_factory=uuid_str, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    fetch_date: date = Field(index=True)
    stories: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    id: str = Field(default_factory=uuid_str, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    report_date: date = Field(index=True)
    report_title: str
    opening_line: str
    closing_line: str
    sections: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    raw_response: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GenerationJob(SQLModel, table=True):
    __tablename__ = "generation_jobs"

    id: str = Field(default_factory=uuid_str, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    # "generate" | "ai-only" | "from-scratch"
    type: str
    # "running" | "completed" | "failed"
    status: str = Field(default="running")
    # Pipeline stage key (e.g. "fetching_news", "triaging", "writing"). Frontend
    # maps this to a human label so the in-progress UI shows useful detail.
    stage: str = Field(default="queued")
    # 0–100 progress within the running job. Set to 100 when status == completed.
    progress: int = Field(default=0)
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    options: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CatchAllJob(SQLModel, table=True):
    """Tracks an async NewsCatcher CatchAll job (submit → poll → pull pipeline).

    On the free plan only one CatchAll job runs at a time across the whole API key,
    so we persist state to: (1) avoid re-submitting while one is in flight,
    (2) reuse completed results for the rest of the day, and (3) let a background
    poller advance jobs without blocking report generation.
    """
    __tablename__ = "catchall_jobs"

    id: str = Field(default_factory=uuid_str, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    # CatchAll's job UUID returned from /catchAll/submit
    job_id: str = Field(index=True)
    # CatchAll pipeline stage: submitted, analyzing, fetching, clustering, enriching, completed, failed
    status: str = Field(default="submitted")
    query: str
    mode: str = Field(default="lite")  # "lite" or "base"
    # Pre-flattened article-shaped records (citations from each cluster). Empty until pull.
    records: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
