"""Enrolment sessions and face templates — INIT.md §6."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

EMBEDDING_DIM = 512


class EnrolmentSession(Base):
    __tablename__ = "enrolment_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE")
    )
    # active|completed|expired|abandoned
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    captured_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # {"front": 4, "left": 3, ...}
    angles_captured: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FaceTemplate(Base):
    __tablename__ = "face_templates"
    __table_args__ = (Index("idx_templates_student", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE")
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    # front|left|right|up|down|centroid
    angle: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_centroid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Real 3D head pose in DEGREES, from MediaPipe's facial transformation matrix (D12).
    # Positive yaw = subject turned to their own left; positive pitch = looking down.
    #
    # Nullable, and that is what keeps this migration non-breaking: rows written before
    # D12 have no degrees to backfill, and centroid rows have none by nature — the mean
    # of five orientations is not an orientation. `load_roster_gallery()` keeps loading
    # every one of them.
    yaw_deg: Mapped[float | None] = mapped_column(Float)
    pitch_deg: Mapped[float | None] = mapped_column(Float)
    roll_deg: Mapped[float | None] = mapped_column(Float)
    # Which landmark set aligned the crop this embedding came from. Distinct from
    # model_version, which names the RECOGNISER and is deliberately unchanged (D12):
    # measured cosine between SCRFD-aligned and MediaPipe-aligned embeddings of the same
    # face is 0.96-0.98, so the two remain comparable and no re-enrolment is forced.
    # This column is what lets a later calibration run separate them and check.
    landmark_source: Mapped[str | None] = mapped_column(String(48))
    # §14.1 — never compare embeddings across model versions.
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # enrolment|feedback
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
