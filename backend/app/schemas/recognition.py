"""Live Test schemas — the single-frame identify response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IdentifyIn(BaseModel):
    image: str = Field(description="data:image/jpeg;base64,... — UNMIRRORED")
    section: str = Field(description="Section code; the gallery is scoped to its roster")


class IdentifiedFace(BaseModel):
    """One detected face. Everything below `quality_score` is null when the
    quality gate rejected the crop — a rejected face is still reported, with its
    reason, so the screen can say what to fix instead of going blank."""

    bbox: list[float]                       # x1, y1, x2, y2 in UNMIRRORED frame pixels
    accepted: bool
    reason: str | None                      # raw gate code; the frontend maps it (§11)
    quality_score: float

    band: str | None                        # confident | uncertain | no_match
    roll_no: str | None                     # withheld on no_match — see the service
    name: str | None
    score: float | None
    margin: float | None
    runner_up_roll: str | None


class Thresholds(BaseModel):
    t_high: float
    t_low: float
    margin_min: float


class IdentifyOut(BaseModel):
    section: str
    faces: list[IdentifiedFace]
    roster_size: int
    gallery_size: int
    thresholds: Thresholds
