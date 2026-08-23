"""Timetable request/response schemas — INIT.md §10."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class SeedResult(BaseModel):
    section: str
    blocks: int


class BlockOut(BaseModel):
    id: uuid.UUID
    section: str
    day_of_week: str
    start_period: int
    end_period: int
    course_code: str
    component: str
    group_code: str
    room: str
    eligible: bool
    ineligible_reason: str | None = None
    time_window: dict | None = None
