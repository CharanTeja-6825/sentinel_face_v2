"""Pose ratios and angle classification — INIT.md §7.4, §13 ("pose
classification for five synthetic landmark sets").

The "front" fixture is the canonical ArcFace 112x112 alignment template, which
is a frontal face by construction. Using it rather than invented numbers means
the zero point of the formula is under test, not just its branching.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.quality import classify_angle, pose_ratios

# [left_eye, right_eye, nose, left_mouth, right_mouth] in image coordinates.
FRONT = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _with_nose(dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    """FRONT with the nose displaced — the projection effect of head rotation.

    Turning toward the subject's own left swings the nose toward image-right
    (+x); pitching down swings it toward the mouth line (+y). See DECISIONS.md
    D5 for the derivation.
    """
    kps = FRONT.copy()
    kps[2] = kps[2] + (dx, dy)
    return kps


def test_canonical_frontal_face_is_centred():
    """The specified formula must read ~0 on a by-construction frontal face."""
    yaw, pitch = pose_ratios(FRONT)
    assert abs(yaw) < 0.05, f"yaw zero point drifted: {yaw}"
    assert abs(pitch) < 0.05, f"pitch zero point drifted: {pitch}"
    assert classify_angle(yaw, pitch) == "front"


def test_positive_yaw_is_subject_left():
    """DECISIONS.md D5: nose toward image-right => subject turned to their own
    left => positive yaw => angle 'left'. Getting this backwards ships a wizard
    that tells students to turn the wrong way."""
    yaw, pitch = pose_ratios(_with_nose(dx=+8.0))
    assert yaw > 0.15
    assert classify_angle(yaw, pitch) == "left"


def test_negative_yaw_is_subject_right():
    yaw, pitch = pose_ratios(_with_nose(dx=-8.0))
    assert yaw < -0.15
    assert classify_angle(yaw, pitch) == "right"


def test_nose_toward_mouth_is_looking_down():
    yaw, pitch = pose_ratios(_with_nose(dy=+6.0))
    assert pitch > 0.20
    assert classify_angle(yaw, pitch) == "down"


def test_nose_toward_eyes_is_looking_up():
    yaw, pitch = pose_ratios(_with_nose(dy=-6.0))
    assert pitch < -0.20
    assert classify_angle(yaw, pitch) == "up"


def test_yaw_sign_inverts_under_mirroring():
    """A mirrored capture inverts yaw — the §7.4 trap. The frontend must send
    unmirrored frames even though the preview is mirrored."""
    kps = _with_nose(dx=+8.0)
    mirrored = kps.copy()
    mirrored[:, 0] = 112.0 - mirrored[:, 0]
    # Mirroring also swaps which eye is image-left / image-right.
    mirrored = mirrored[[1, 0, 2, 4, 3]]
    assert pose_ratios(kps)[0] == pytest.approx(-pose_ratios(mirrored)[0], abs=1e-5)


@pytest.mark.parametrize(
    "yaw,pitch,expected",
    [
        (0.0, 0.0, "front"),
        (0.149, 0.199, "front"),   # just inside the front box
        (0.15, 0.0, "left"),       # boundary, inclusive
        (-0.15, 0.0, "right"),
        (0.0, -0.20, "up"),
        (0.0, 0.20, "down"),
    ],
)
def test_classification_boundaries(yaw, pitch, expected):
    assert classify_angle(yaw, pitch) == expected
