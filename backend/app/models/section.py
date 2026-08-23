"""Sections and timetable blocks — INIT.md §6."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TimetableBlock(Base):
    __tablename__ = "timetable_blocks"
    # This constraint is what makes the seed loader idempotent (§9.4).
    __table_args__ = (
        UniqueConstraint("section_id", "day_of_week", "start_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE")
    )
    day_of_week: Mapped[str] = mapped_column(String(3), nullable=False)  # Mon..Sat
    start_period: Mapped[int] = mapped_column(Integer, nullable=False)
    end_period: Mapped[int] = mapped_column(Integer, nullable=False)
    course_code: Mapped[str] = mapped_column(String(32), nullable=False)
    component: Mapped[str] = mapped_column(CHAR(1), nullable=False)  # L|P|S
    group_code: Mapped[str] = mapped_column(String(16), nullable=False)
    room: Mapped[str] = mapped_column(String(32), nullable=False)
