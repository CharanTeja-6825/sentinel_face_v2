"""Evidence and the attendance ledger — INIT.md §6.

Two invariants the code must preserve (§6):

1. `observations` is APPEND-ONLY within a processing run. It is the replay
   buffer: when thresholds change, decisions are re-derived from stored
   observations instead of reprocessing video. That is what makes threshold
   calibration (§12 Phase 6) possible at all. Never UPDATE a row here.
   Re-processing a session deletes the previous run's rows wholesale and
   writes a fresh set (§8.7) — that is a replacement, not a mutation.

2. `attendance_decisions` is unique on (session_id, student_id). Every write
   goes through INSERT ... ON CONFLICT DO UPDATE so retries never duplicate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
    )
    cluster_id: Mapped[int | None] = mapped_column(Integer)
    first_seen_s: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen_s: Mapped[float] = mapped_column(Float, nullable=False)
    crop_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_quality: Mapped[float] = mapped_column(Float, nullable=False)
    best_crop_path: Mapped[str | None] = mapped_column(Text)

    # ── §23 observability ──
    #
    # `crop_count` is how many observations SURVIVED the quality gate and were
    # retained; `observation_count` is how many the track absorbed in total, and
    # `reject_reasons` says what happened to the difference. That gap is the whole
    # diagnostic: a track with 200 observations and 2 survivors, all rejected
    # `face_too_small`, is a camera-placement problem, not a threshold problem
    # (spec §25).
    #
    # All nullable — rows written before migration 0003 have no such numbers, and
    # inventing a default would make a pre-existing run look measured.
    observation_count: Mapped[int | None] = mapped_column(Integer)
    resolution_band: Mapped[str | None] = mapped_column(String(16))
    mean_face_width_px: Mapped[float | None] = mapped_column(Float)
    mean_blur: Mapped[float | None] = mapped_column(Float)
    mean_brightness: Mapped[float | None] = mapped_column(Float)
    reject_reasons: Mapped[dict | None] = mapped_column(JSONB)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
    )
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    top1_student_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id")
    )
    top1_score: Mapped[float | None] = mapped_column(Float)
    top2_student_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id")
    )
    top2_score: Mapped[float | None] = mapped_column(Float)
    margin: Mapped[float | None] = mapped_column(Float)
    # confident|uncertain|no_match
    band: Mapped[str] = mapped_column(String(16), nullable=False)
    crop_paths: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AttendanceDecision(Base):
    __tablename__ = "attendance_decisions"
    # Makes writes idempotent — see invariant 2 above.
    __table_args__ = (UniqueConstraint("session_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id")
    )
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # present|absent
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # auto|manual_override
    score: Mapped[float | None] = mapped_column(Float)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UnmatchedFace(Base):
    __tablename__ = "unmatched_faces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
    )
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_path: Mapped[str] = mapped_column(Text, nullable=False)
    best_score: Mapped[float | None] = mapped_column(Float)
    # unresolved|outsider|unenrolled|not_a_person
    resolution: Mapped[str | None] = mapped_column(String(20), default="unresolved")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
