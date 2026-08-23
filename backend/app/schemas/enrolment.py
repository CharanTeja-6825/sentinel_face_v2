"""Enrolment schemas — INIT.md §10."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionIn(BaseModel):
    roll_no: str
    consent: bool = False


class CreateSessionOut(BaseModel):
    session_id: uuid.UUID
    student_id: uuid.UUID
    required_angles: list[str]
    min_samples: int
    min_samples_per_angle: int
    # The angle the wizard must prompt for first. Every /frames response
    # carries the current one, so the client never computes the stage itself.
    target_angle: str | None
    expires_at: datetime


class FrameIn(BaseModel):
    image: str = Field(description="data:image/jpeg;base64,... — UNMIRRORED")


class Pose(BaseModel):
    """Real 3D head pose in degrees (D12).

    Positive yaw = the subject turned to their own left; positive pitch = looking down.
    Angle labels are in the SUBJECT's frame, which is what "turn your head left" means
    to a student.
    """

    yaw: float
    pitch: float
    roll: float


class FrameOut(BaseModel):
    accepted: bool
    reason: str | None
    # The pose actually seen. Set even on a `wrong_angle` rejection — that is
    # what lets the wizard say which way to turn.
    detected_angle: str | None
    quality_score: float
    captured_count: int
    angle_progress: dict[str, int]
    can_complete: bool
    # The angle to prompt for NEXT, after this frame was applied. None once
    # every requirement is met.
    target_angle: str | None
    min_samples_per_angle: int

    # ── D12 additions. All optional: null whenever the frame never reached the stage
    # that produces them (no face found, buffer full), so no client breaks on absence.
    pose: Pose | None = None
    # Curated landmark rings in NORMALISED [0, 1] coordinates, for the wizard overlay:
    # face oval, both eye contours, outer lips. ~88 points, not all 478 — at a 700 ms
    # probe rate nobody can count mesh vertices, and the full set is ~5x the payload.
    #
    # These are coordinates in the UNMIRRORED frame the client POSTed. The preview is
    # CSS-mirrored, so the overlay must be mirrored with it (D5).
    landmarks: dict[str, list[list[float]]] | None = None
    eyes_open: bool | None = None


class CompleteOut(BaseModel):
    student_id: uuid.UUID
    stored_templates: int
    angles: dict[str, int]


class SessionStateOut(BaseModel):
    session_id: uuid.UUID
    student_id: uuid.UUID
    status: str
    captured_count: int
    angle_progress: dict[str, int]
    can_complete: bool
    target_angle: str | None
    expires_at: datetime
    required_angles: list[str]
    min_samples: int
    min_samples_per_angle: int
