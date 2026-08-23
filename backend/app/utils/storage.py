"""File paths and crop persistence — INIT.md §4, §8."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import cv2
import numpy as np

from app.config import settings


def video_path(session_id: uuid.UUID, suffix: str = ".mp4") -> Path:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    return settings.videos_dir / f"{session_id}{suffix}"


def session_crop_dir(session_id: uuid.UUID) -> Path:
    return settings.crops_dir / str(session_id)


def clear_session_crops(session_id: uuid.UUID) -> None:
    """Re-processing replaces evidence rather than accumulating it (§8.7)."""
    shutil.rmtree(session_crop_dir(session_id), ignore_errors=True)


def save_crop(
    session_id: uuid.UUID, cluster_id: int, index: int, image: np.ndarray
) -> str:
    """Write one evidence crop, returning a path relative to the crops root.

    Relative because it is stored in the database and served under /crops —
    an absolute container path would not survive a move.
    """
    directory = session_crop_dir(session_id) / str(cluster_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{index:04d}.jpg"
    cv2.imwrite(str(directory / filename), image)
    return f"{session_id}/{cluster_id}/{filename}"


def crop_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return f"{settings.public_base_url.rstrip('/')}/crops/{relative_path}"
