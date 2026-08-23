"""Frame preprocessing — D13.

The claim these defend is narrow and worth stating: preprocessing must MEASURABLY
improve a badly-lit frame, and must LEAVE A GOOD FRAME ALONE. A pipeline that mangles
already-good input in the name of enhancement is worse than none, because every
enrolment frame goes through it.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.config import settings
from app.services.preprocess import (
    adaptive_gamma,
    clahe_on_luminance,
    enhance,
    fit_to_max_side,
)


def face_like(brightness: float = 0.5, size: int = 240) -> np.ndarray:
    """A synthetic frame with real local structure, not flat noise.

    Flat noise cannot show CLAHE working — local contrast enhancement needs local
    contrast to enhance. Concentric blobs plus texture stand in for a face.
    """
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    base = 0.5 + 0.35 * np.sin(6 * np.pi * xx) * np.cos(6 * np.pi * yy)
    base += 0.08 * rng.standard_normal((size, size))
    base = np.clip(base * (brightness / 0.5), 0, 1)
    return cv2.cvtColor((base * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def luma(bgr: np.ndarray) -> float:
    return float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()) / 255.0


# ─────────────────────────── shape and dtype ────────────────────────────


def test_enhance_preserves_shape_and_dtype():
    src = face_like()
    out, _ = enhance(src)
    assert out.shape == src.shape
    assert out.dtype == np.uint8


def test_enhance_does_not_mutate_its_input():
    """`submit_frame` embeds the ORIGINAL pixels after enhancing a copy (D13). If
    enhance() wrote through, ArcFace would silently receive enhanced input and every
    stored template would depend on the preprocessing parameters."""
    src = face_like(brightness=0.2)
    before = src.copy()
    enhance(src)
    assert np.array_equal(src, before)


def test_disabled_is_a_passthrough():
    cfg = settings.preprocess.model_copy(update={"enabled": False})
    src = face_like()
    out, info = enhance(src, cfg)
    assert out is src
    assert info == {"enabled": False}


# ────────────────────────── adaptive gamma ──────────────────────────────


def test_dark_frame_is_brightened_toward_the_target():
    dark = face_like(brightness=0.15)
    out, gamma = adaptive_gamma(dark, settings.preprocess.gamma_target_luma)
    assert gamma < 1.0, "brightening requires gamma below 1"
    assert luma(out) > luma(dark)
    assert abs(luma(out) - settings.preprocess.gamma_target_luma) < abs(
        luma(dark) - settings.preprocess.gamma_target_luma
    )


def test_bright_frame_is_darkened_toward_the_target():
    bright = face_like(brightness=0.85)
    out, gamma = adaptive_gamma(bright, settings.preprocess.gamma_target_luma)
    assert gamma > 1.0
    assert luma(out) < luma(bright)


def test_a_well_exposed_frame_is_left_alone():
    """The no-op case has to actually be a no-op — this runs on every probe."""
    good = face_like(brightness=settings.preprocess.gamma_target_luma)
    out, gamma = adaptive_gamma(good, settings.preprocess.gamma_target_luma)
    assert gamma == 1.0
    assert out is good


@pytest.mark.parametrize("value", [0, 255])
def test_unrecoverable_frames_are_not_gamma_corrected(value):
    """Pure black or pure white has no exposure to recover; log() would blow up."""
    flat = np.full((64, 64, 3), value, np.uint8)
    out, gamma = adaptive_gamma(flat, settings.preprocess.gamma_target_luma)
    assert gamma == 1.0
    assert out is flat


def test_gamma_is_clamped():
    """A frame far outside range is clamped rather than fully "corrected" — past the
    clamp the correction manufactures detail that was never captured."""
    very_dark = np.full((64, 64, 3), 3, np.uint8)
    _, gamma = adaptive_gamma(very_dark, 0.45)
    assert gamma == pytest.approx(0.5)


# ──────────────────────────────── CLAHE ─────────────────────────────────


def test_clahe_raises_local_contrast():
    low = face_like(brightness=0.35)
    out = clahe_on_luminance(low, settings.preprocess.clahe_clip, settings.preprocess.clahe_grid)
    before = cv2.cvtColor(low, cv2.COLOR_BGR2GRAY).std()
    after = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).std()
    assert after > before, f"CLAHE reduced contrast: {before:.1f} -> {after:.1f}"


def test_clahe_leaves_chroma_alone():
    """Equalising RGB channels independently is what produces the classic colour cast.
    Operating on LAB's L only must leave a and b untouched."""
    src = face_like(brightness=0.4)
    # Give the frame an actual colour so a shift would be visible.
    src[:, :, 2] = np.clip(src[:, :, 2].astype(int) + 40, 0, 255).astype(np.uint8)
    a_before = cv2.cvtColor(src, cv2.COLOR_BGR2LAB)[:, :, 1:]
    a_after = cv2.cvtColor(
        clahe_on_luminance(src, settings.preprocess.clahe_clip, settings.preprocess.clahe_grid),
        cv2.COLOR_BGR2LAB,
    )[:, :, 1:]
    # LAB round-trips through uint8, so allow rounding but not a shift.
    assert np.abs(a_before.astype(int) - a_after.astype(int)).mean() < 1.5


# ──────────────────────────── downscaling ───────────────────────────────


def test_fit_to_max_side_reports_a_usable_scale():
    """`scale` is what maps landmarks back to full-resolution coordinates. If it is
    wrong, the crop ArcFace embeds is off the face."""
    src = np.zeros((720, 1280, 3), np.uint8)
    small, scale = fit_to_max_side(src, 640)
    assert max(small.shape[:2]) == 640
    assert small.shape[1] == pytest.approx(1280 * scale, abs=1)
    # A point at the centre of the small image maps back to the centre of the original.
    assert (small.shape[1] / 2) / scale == pytest.approx(640, abs=1)


def test_small_frames_are_not_upscaled():
    src = np.zeros((200, 300, 3), np.uint8)
    out, scale = fit_to_max_side(src, 640)
    assert out is src
    assert scale == 1.0


# ────────────────────── the whole pipeline together ─────────────────────


def test_a_dim_frame_comes_out_better_on_both_axes():
    """The end-to-end claim: brighter AND with more local contrast."""
    dim = face_like(brightness=0.18)
    out, info = enhance(dim)
    assert info["enabled"] and info["gamma"] < 1.0
    assert info["mean_luma_after"] > info["mean_luma_before"]
    assert cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).std() > cv2.cvtColor(dim, cv2.COLOR_BGR2GRAY).std()
