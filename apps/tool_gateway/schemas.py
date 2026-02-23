"""Pydantic schemas for tool gateway."""

from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel, Field, field_validator

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


class ToolError(BaseModel):
    message: str
    code: str | None = None


class ToolEnvelope(BaseModel):
    success: bool
    data: dict[str, object] | None = None
    error: ToolError | None = None
    trace_id: str
    content: list[dict[str, str]] | None = None


class GithubListOpenPrsRequest(BaseModel):
    owner: str
    repo: str
    per_page: int = Field(default=20, ge=1, le=100)


class GithubCommitStatsRequest(BaseModel):
    owner: str
    repo: str
    since: datetime
    until: datetime

    @field_validator("until")
    @classmethod
    def _validate_until(cls, value: datetime, info):
        since = info.data.get("since")
        if isinstance(since, datetime) and value <= since:
            raise ValueError("until must be greater than since")
        return value


class GithubRepoActivityRequest(BaseModel):
    owner: str
    repo: str
    hours: int = Field(default=24, ge=1, le=168)


class GithubCommentPrRequest(BaseModel):
    owner: str
    repo: str
    prNumber: int = Field(ge=1)
    body: str = Field(min_length=1)
    dryRun: bool = True


class InternalActionRequest(BaseModel):
    dryRun: bool = True
    section_title: str | None = None
    document_id: str | None = None
