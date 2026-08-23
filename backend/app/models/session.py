"""Attendance sessions — INIT.md §6."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# created|uploaded|queued|processing|completed|failed|finalized
SESSION_STATUSES = (
    "created",
    "uploaded",
    "queued",
    "processing",
    "completed",
    "failed",
    "finalized",
)


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        UniqueConstraint("section_id", "session_date", "start_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("timetable_blocks.id")
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id")
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_period: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    video_path: Mapped[str | None] = mapped_column(Text)
    video_duration_s: Mapped[float | None] = mapped_column(Float)
    expected_count: Mapped[int | None] = mapped_column(Integer)
    detected_count: Mapped[int | None] = mapped_column(Integer)
    frames_sampled: Mapped[int | None] = mapped_column(Integer)
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
