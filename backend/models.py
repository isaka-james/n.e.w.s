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
