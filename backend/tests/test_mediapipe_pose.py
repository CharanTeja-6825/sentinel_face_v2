"""MediaPipe pose and angle bucketing — D12.

DECISIONS.md D5 exists because a wrong yaw sign tells every student to turn the wrong
way and produces a plausible-looking gallery with no error anywhere. Swapping the pose
estimator re-opens exactly that question, so it was re-resolved the same way D5 was —
by mirroring real faces — and it is pinned here.

The measured result: MediaPipe's frame already agrees with D5 on both axes, so
`pose_degrees()` applies no correction. That is the fact these tests defend. If someone
later "fixes" a sign, these fail.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import settings
from app.services.quality import classify_angle_deg

pose_degrees = pytest.importorskip(
    "app.services.mp_face", reason="mediapipe not installed"
).pose_degrees


def rotation(yaw_deg: float = 0.0, pitch_deg: float = 0.0, roll_deg: float = 0.0):
    """A 4x4 transform of the shape MediaPipe emits, for a known rotation.

    Built as R = Rz(roll) @ Ry(yaw) @ Rx(pitch), which is the composition
    cv2.RQDecomp3x3 inverts — determined by trying all six orderings and keeping the
    one that round-trips to zero error. Euler angles are order-dependent, so a builder
    in any other order round-trips wrong the moment two axes are non-zero, and the test
    would be measuring its own arithmetic rather than pose_degrees().
    """
    x, y, z = np.deg2rad([pitch_deg, yaw_deg, roll_deg])
    rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = rz @ ry @ rx
    return m


# ───────────────────────── pose_degrees round-trip ──────────────────────


def test_identity_transform_is_frontal():
    yaw, pitch, roll = pose_degrees(np.eye(4))
    assert abs(yaw) < 1e-6 and abs(pitch) < 1e-6 and abs(roll) < 1e-6
    assert classify_angle_deg(yaw, pitch) == "front"


@pytest.mark.parametrize("yaw", [-30.0, -15.0, 0.0, 15.0, 30.0])
@pytest.mark.parametrize("pitch", [-20.0, 0.0, 20.0])
def test_decomposition_recovers_the_angles_it_was_given(yaw, pitch):
    got_yaw, got_pitch, got_roll = pose_degrees(rotation(yaw_deg=yaw, pitch_deg=pitch))
    assert got_yaw == pytest.approx(yaw, abs=0.5)
    assert got_pitch == pytest.approx(pitch, abs=0.5)
    assert got_roll == pytest.approx(0.0, abs=0.5)


def test_roll_is_recovered_at_all():
    """The 5-keypoint estimator could not measure roll. This one must."""
    _, _, roll = pose_degrees(rotation(roll_deg=25.0))
    assert roll == pytest.approx(25.0, abs=0.5)


# ─────────────── the sign convention (D5, re-verified for D12) ──────────


def test_positive_yaw_is_subject_left():
    """Measured on real faces: a face whose nose has swung toward image-left — the
    subject turned to their own RIGHT — reads negative. So positive is their left,
    matching D5 and matching what the wizard prompt "turn your head to your left" means.
    """
    yaw, pitch, _ = pose_degrees(rotation(yaw_deg=+25.0))
    assert yaw > settings.quality.angle_yaw_deg
    assert classify_angle_deg(yaw, pitch) == "left"


def test_negative_yaw_is_subject_right():
    yaw, pitch, _ = pose_degrees(rotation(yaw_deg=-25.0))
    assert yaw < -settings.quality.angle_yaw_deg
    assert classify_angle_deg(yaw, pitch) == "right"


def test_negative_pitch_is_chin_up():
    """Verified against a real frame that read -19.3 deg with the chin visibly raised
    and the nose only 21% of the way down the eye-to-chin span (chin-up foreshortening).
    Same convention as `classify_angle()`, which returns "up" for pitch <= -0.20.
    """
    yaw, pitch, _ = pose_degrees(rotation(pitch_deg=-25.0))
    assert pitch < -settings.quality.angle_pitch_deg
    assert classify_angle_deg(yaw, pitch) == "up"


def test_positive_pitch_is_looking_down():
    yaw, pitch, _ = pose_degrees(rotation(pitch_deg=+25.0))
    assert classify_angle_deg(yaw, pitch) == "down"


def test_yaw_sign_inverts_under_mirroring():
    """Mirroring a frame must invert yaw and leave pitch alone.

    This is the property D5 was established with, and it is what makes the frontend's
    "preview is mirrored, canvas is not" rule load-bearing. Mirroring negates the world
    x-axis, i.e. R -> M @ R @ M with M = diag(-1, 1, 1).
    """
    m = np.diag([-1.0, 1.0, 1.0])
    original = rotation(yaw_deg=+22.0, pitch_deg=+8.0)
    mirrored = original.copy()
    mirrored[:3, :3] = m @ original[:3, :3] @ m

    yaw_a, pitch_a, _ = pose_degrees(original)
    yaw_b, pitch_b, _ = pose_degrees(mirrored)

    assert yaw_a * yaw_b < 0, f"yaw did not invert: {yaw_a} -> {yaw_b}"
    assert yaw_b == pytest.approx(-yaw_a, abs=0.5)
    assert pitch_b == pytest.approx(pitch_a, abs=0.5)


# ───────────────────────── angle bucketing ──────────────────────────────


def test_front_is_the_dead_zone():
    assert classify_angle_deg(0.0, 0.0) == "front"
    assert classify_angle_deg(14.9, 11.9) == "front"


def test_the_more_extreme_axis_wins():
    """The bug this replaces: `classify_angle()` tests yaw before pitch, so a face at
    yaw 16 / pitch 30 was labelled "left" and "down" was unreachable for anyone who
    tilted without keeping their head perfectly straight.
    """
    # yaw 16/15 = 1.07 excess, pitch 30/12 = 2.5 excess -> pitch wins.
    assert classify_angle_deg(16.0, 30.0) == "down"
    assert classify_angle_deg(16.0, -30.0) == "up"
    # And the other way round, so the fix is not just "pitch always wins".
    assert classify_angle_deg(40.0, 13.0) == "left"
    assert classify_angle_deg(-40.0, 13.0) == "right"


@pytest.mark.parametrize(
    "yaw,pitch,expected",
    [
        (20.0, 0.0, "left"),
        (-20.0, 0.0, "right"),
        (0.0, 20.0, "down"),
        (0.0, -20.0, "up"),
    ],
)
def test_each_required_angle_is_reachable(yaw, pitch, expected):
    """Every angle in required_angles must be produced by some pose, or the guided
    session deadlocks on a quota that cannot be filled."""
    assert classify_angle_deg(yaw, pitch) == expected
    assert expected in settings.enrolment.required_angles
