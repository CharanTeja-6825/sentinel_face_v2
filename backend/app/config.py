"""Configuration — INIT.md §5.

Single source of truth for every threshold in the system. INIT.md §0.6:
"Every threshold in this document goes in config.py reading from environment
or YAML. Never hardcode a threshold in business logic."

Import `settings` and read from it. Do not copy values out into constants.
"""

from __future__ import annotations

import logging
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


# ─────────────────────────── thresholds.yaml ───────────────────────────


class QualityConfig(BaseModel):
    min_det_score: float
    min_face_width_px: int
    min_blur_variance: float
    # Ratio gates — the 5-keypoint estimator. The VIDEO path still reads these.
    max_yaw_ratio: float
    max_pitch_ratio: float
    min_brightness: float
    max_brightness: float
    # Degree gates — MediaPipe 3D pose, enrolment path only (D12). Real degrees, so
    # unlike the ratios above these mean something a human can reason about.
    max_yaw_deg: float
    max_pitch_deg: float
    max_roll_deg: float
    angle_yaw_deg: float
    angle_pitch_deg: float
    max_eye_blink: float


class PreprocessConfig(BaseModel):
    """D13 — applied to the detection/landmark copy only, never to what ArcFace embeds."""

    enabled: bool
    max_side: int
    bilateral_d: int
    bilateral_sigma: float
    gamma_target_luma: float
    clahe_clip: float
    clahe_grid: int


class EnrolmentConfig(BaseModel):
    min_samples: int
    max_samples: int
    required_angles: list[str]
    min_samples_per_angle: int
    min_quality_score: float
    diversity_max_cosine: float
    session_timeout_minutes: int


class VideoConfig(BaseModel):
    sample_fps: float
    max_duration_minutes: float
    max_upload_mb: int
    det_size: tuple[int, int]
    track_iou_threshold: float
    track_max_age_frames: int
    track_min_hits: int


class MatchingConfig(BaseModel):
    cluster_distance: float
    min_crops_per_track: int
    t_high: float
    t_low: float
    margin_min: float


class Thresholds(BaseModel):
    quality: QualityConfig
    preprocess: PreprocessConfig
    enrolment: EnrolmentConfig
    video: VideoConfig
    matching: MatchingConfig


# ──────────────────────────── periods.yaml ─────────────────────────────


class Period(BaseModel):
    start: time
    end: time


class Periods(BaseModel):
    # False until a human confirms the clock times with the institution.
    # INIT.md §5.2 flags these as placeholders.
    verified: bool = False
    timezone: str
    period_duration_minutes: int
    periods: dict[int, Period]
    attendance_eligible_periods: list[int]


# ─────────────────────────────── settings ──────────────────────────────


class Settings(BaseSettings):
    # protected_namespaces=() because MODEL_ROOT / model_version are ours, not
    # pydantic's — without this pydantic warns on every import.
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    database_url: str = "postgresql+psycopg://sentinel:sentinel@db:5432/sentinelface"
    redis_url: str = "redis://redis:6379/0"

    config_dir: Path = Path("/config")
    storage_dir: Path = Path("/storage")
    model_root: Path = Path("/storage/models")

    # -1 = CPU, 0 = first GPU.
    ctx_id: int = -1

    # SCRFD input size for the enrolment path (webcam frames, subject close to
    # the lens). The video path uses thresholds.yaml video.det_size instead,
    # which must scale with source resolution — see §8.3 and §14.4.
    enrolment_det_size: tuple[int, int] = (640, 640)

    cors_origins: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:8000"

    app_version: str = "0.1.0"

    # RQ queue name for video jobs.
    video_queue: str = "video_jobs"

    _thresholds: Thresholds | None = None
    _periods: Periods | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def _load_yaml(self, name: str) -> dict[str, Any]:
        path = self.config_dir / name
        if not path.exists():
            raise FileNotFoundError(
                f"Missing config file {path}. Mount ./config to {self.config_dir}."
            )
        with path.open() as fh:
            return yaml.safe_load(fh)

    @property
    def thresholds(self) -> Thresholds:
        if self._thresholds is None:
            object.__setattr__(
                self, "_thresholds", Thresholds(**self._load_yaml("thresholds.yaml"))
            )
        return self._thresholds  # type: ignore[return-value]

    @property
    def periods(self) -> Periods:
        if self._periods is None:
            object.__setattr__(
                self, "_periods", Periods(**self._load_yaml("periods.yaml"))
            )
        return self._periods  # type: ignore[return-value]

    # Convenience accessors so business logic reads settings.quality.* directly.
    @property
    def quality(self) -> QualityConfig:
        return self.thresholds.quality

    @property
    def preprocess(self) -> PreprocessConfig:
        return self.thresholds.preprocess

    @property
    def enrolment(self) -> EnrolmentConfig:
        return self.thresholds.enrolment

    @property
    def video(self) -> VideoConfig:
        return self.thresholds.video

    @property
    def matching(self) -> MatchingConfig:
        return self.thresholds.matching

    @property
    def videos_dir(self) -> Path:
        return self.storage_dir / "videos"

    @property
    def crops_dir(self) -> Path:
        return self.storage_dir / "crops"

    def warn_if_unverified(self) -> None:
        """INIT.md §5.2 — periods.yaml clock times are a placeholder until a
        human confirms them. Say so loudly rather than pretending otherwise."""
        if not self.periods.verified:
            log.warning(
                "=" * 78 + "\n"
                "config/periods.yaml is UNVERIFIED. The period clock times are the "
                "INIT.md §5.2 placeholder and are probably wrong for your "
                "institution.\nThis affects displayed time windows only — "
                "attendance keys off period NUMBERS, not clock times.\n"
                "Confirm the times with the university, then set `verified: true`.\n"
                + "=" * 78
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
