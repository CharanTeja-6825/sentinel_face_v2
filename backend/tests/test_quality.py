"""Quality gate at each threshold boundary — INIT.md §7.3, §13.

Uses a fake Face object so each check can be driven to its boundary
independently. A real-model smoke test lives at the bottom and is skipped when
the model is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import pytest

from app.config import settings
from app.services import quality
from app.services.quality import assess

CFG = settings.quality


@dataclass
class FakeFace:
    bbox: np.ndarray
    kps: np.ndarray
    det_score: float


def frontal_kps(x1: float, y1: float, width: float) -> np.ndarray:
    """Canonical frontal landmarks scaled into a bbox at (x1, y1)."""
    base = np.array(
        [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
         [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32
    )
    return base * (width / 112.0) + (x1, y1)


def make_face(width=120.0, det_score=0.95, x1=50.0, y1=50.0) -> FakeFace:
    return FakeFace(
        bbox=np.array([x1, y1, x1 + width, y1 + width], dtype=np.float32),
        kps=frontal_kps(x1, y1, width),
        det_score=det_score,
    )


def sharp_frame(h=400, w=400, brightness=128) -> np.ndarray:
    """Noise gives a high Laplacian variance — i.e. a sharp image."""
    rng = np.random.default_rng(0)
    noise = rng.integers(-40, 40, size=(h, w, 3))
    return np.clip(noise + brightness, 0, 255).astype(np.uint8)


# ───────────────────────────── each check ──────────────────────────────


def test_accepts_a_good_face():
    r = assess(make_face(), sharp_frame())
    assert r.accepted, r.reason
    assert r.angle == "front"
    assert 0.0 <= r.quality_score <= 1.0


def test_rejects_low_detection_confidence():
    r = assess(make_face(det_score=CFG.min_det_score - 0.01), sharp_frame())
    assert not r.accepted and r.reason == quality.LOW_DETECTION


def test_accepts_at_detection_boundary():
    assert assess(make_face(det_score=CFG.min_det_score), sharp_frame()).accepted


def test_rejects_face_too_small():
    r = assess(make_face(width=CFG.min_face_width_px - 1), sharp_frame())
    assert not r.accepted and r.reason == quality.TOO_SMALL


def test_accepts_at_size_boundary():
    assert assess(make_face(width=CFG.min_face_width_px), sharp_frame()).accepted


def test_rejects_blurred_face():
    """Deliberately blurred input must be rejected — §7.7."""
    frame = cv2.GaussianBlur(sharp_frame(), (31, 31), 0)
    r = assess(make_face(), frame)
    assert not r.accepted and r.reason == quality.TOO_BLURRY


def test_blur_metric_does_not_move_with_face_size():
    """The sharpness metric must not depend on how big the face is.

    Regression: the raw variance of the Laplacian is a per-pixel second
    derivative, so photographing the SAME face closer spreads each edge over
    more pixels and lowers the score. Measured raw, one real crop scored 1585
    at 60 px and 123 at 600 px — so a 1100 px close-up was rejected
    `too_blurry` while a tiny back-row face passed. Every face in a phone-shot
    video was silently discarded before embedding.

    A metric that swings 13x with subject distance makes cfg.min_blur_variance
    meaningless, so this pins the scale-invariance, not a specific number.
    """
    # Structure at a scale RELATIVE to the subject, the way eyes and a mouth
    # are. Per-pixel noise would not do: its detail sits at the Nyquist limit,
    # so downscaling averages it to nothing and the test would measure the
    # fixture rather than the metric.
    rng = np.random.default_rng(1)
    blocks = rng.integers(0, 255, size=(16, 16), dtype=np.uint16).astype(np.uint8)
    detail = cv2.resize(blocks, (1200, 1200), interpolation=cv2.INTER_NEAREST)

    scores = [
        quality.blur_variance(
            cv2.resize(detail, (w, w), interpolation=cv2.INTER_AREA)
        )
        for w in (60, 150, 300, 600, 1200)
    ]
    # The bug had two halves, and both are pinned here.
    # 1. Magnitude: the raw metric swung ~13x across these sizes.
    assert max(scores) / min(scores) < 4.0, scores
    # 2. Direction: raw scored the LARGEST face lowest, which is what pushed
    #    close-ups below the threshold. Bigger must never mean blurrier.
    assert scores[-1] >= scores[0], scores
    # ...and every size reads as sharp, which is what they are.
    assert min(scores) > CFG.min_blur_variance, scores


def test_blur_metric_still_separates_sharp_from_blurred():
    """Scale-invariance must not have cost us the ability to detect blur."""
    sharp = cv2.cvtColor(sharp_frame(600, 600), cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(sharp, (31, 31), 0)
    assert quality.blur_variance(sharp) > CFG.min_blur_variance
    assert quality.blur_variance(blurred) < CFG.min_blur_variance


def test_accepts_a_large_close_up_face():
    """A big, sharp face is the easy case and must never be rejected."""
    r = assess(make_face(width=900.0, x1=50.0, y1=50.0), sharp_frame(1200, 1200))
    assert r.accepted, r.reason


def test_rejects_too_dark():
    frame = np.full((400, 400, 3), int(CFG.min_brightness) - 10, dtype=np.uint8)
    # Flat fill is also blurry, so add texture to isolate the brightness check.
    frame[::2, ::2] = 0
    frame[1::2, 1::2] = int(CFG.min_brightness) * 2 - 10
    r = assess(make_face(), frame)
    assert not r.accepted and r.reason in (quality.POOR_LIGHTING, quality.TOO_BLURRY)


def test_rejects_too_bright():
    frame = sharp_frame(brightness=250)
    r = assess(make_face(), frame)
    assert not r.accepted and r.reason == quality.POOR_LIGHTING


def test_rejects_extreme_yaw():
    face = make_face()
    face.kps[2, 0] += 40  # swing the nose far toward image-right
    r = assess(face, sharp_frame())
    assert not r.accepted and r.reason == quality.EXTREME_POSE


def test_quality_score_rises_with_quality():
    small = assess(make_face(width=CFG.min_face_width_px, det_score=0.62), sharp_frame())
    large = assess(make_face(width=300, det_score=0.99), sharp_frame())
    assert small.accepted and large.accepted
    assert large.quality_score > small.quality_score


# ───────────────────────── real-model smoke test ───────────────────────


def test_real_embedding_is_512d_unit_vector(engine_loaded):
    """Phase 2 done-when: a JPEG embeds to a 512-D unit vector."""
    from insightface.data import get_image

    img = get_image("t1")
    faces = engine_loaded.detect(img)
    assert faces, "no faces detected in the bundled sample image"
    for f in faces:
        v = engine_loaded.embedding_of(f)
        assert v.shape == (512,)
        # §14.8 — .normed_embedding, so cosine similarity is a plain dot product.
        assert np.linalg.norm(v) == pytest.approx(1.0, abs=1e-5)


def test_real_face_downscaled_is_rejected_as_too_small(engine_loaded):
    """A face far from the camera must be rejected with face_too_small — §7.7."""
    from insightface.data import get_image

    img = get_image("t1")
    faces = engine_loaded.detect(img)
    assert faces
    f = max(faces, key=lambda x: x.bbox[2] - x.bbox[0])

    shrink = (CFG.min_face_width_px - 5) / (f.bbox[2] - f.bbox[0])
    small = cv2.resize(img, None, fx=shrink, fy=shrink)
    scaled = FakeFace(
        bbox=np.asarray(f.bbox) * shrink,
        kps=np.asarray(f.kps) * shrink,
        det_score=float(f.det_score),
    )
    r = assess(scaled, small)
    assert not r.accepted and r.reason == quality.TOO_SMALL
