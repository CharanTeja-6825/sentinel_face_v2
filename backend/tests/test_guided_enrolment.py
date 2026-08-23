"""Guided capture — the registration pipeline's staging rule.

The behaviour under test is that a session asks for exactly ONE orientation at
a time and refuses frames showing any other, so the resulting gallery is even
across `required_angles` instead of being whatever the student happened to be
doing while the shutter fired.

`target_angle()` is a pure function of the buffer, so most of this needs no
database, no model and no HTTP. The one case that does — a frame arriving for
the wrong angle — is driven through the real endpoint with the scripted engine
from test_enrolment_flow, because the interesting part is the response the
wizard receives.
"""

from __future__ import annotations

from app.config import settings
from app.services.enrolment_service import BufferedSample, can_complete, target_angle

from .test_enrolment_flow import scripted, session_id, sharp_jpeg_data_url, student  # noqa: F401

CFG = settings.enrolment


def buffer(**counts: int) -> list[BufferedSample]:
    return [
        BufferedSample(embedding=[0.0] * 512, angle=angle, quality_score=0.9)
        for angle, n in counts.items()
        for _ in range(n)
    ]


def test_first_target_is_the_first_required_angle():
    assert target_angle([]) == CFG.required_angles[0]


def test_target_holds_until_the_angle_meets_its_quota():
    first, second = CFG.required_angles[0], CFG.required_angles[1]
    for n in range(CFG.min_samples_per_angle):
        assert target_angle(buffer(**{first: n})) == first
    # Quota met -> and only then does the wizard move on.
    assert target_angle(buffer(**{first: CFG.min_samples_per_angle})) == second


def test_angles_are_walked_in_required_order():
    seen, samples = [], []
    # Feed exactly what the target asks for, and record the sequence.
    while (angle := target_angle(samples)) is not None:
        seen.append(angle)
        samples.append(
            BufferedSample(embedding=[0.0] * 512, angle=angle, quality_score=0.9)
        )
        assert len(samples) <= CFG.max_samples, "guided capture failed to terminate"

    # Each angle is asked for as one contiguous run, in configured order.
    runs = [a for i, a in enumerate(seen) if i == 0 or seen[i - 1] != a]
    assert runs == CFG.required_angles[: len(runs)]
    assert can_complete(samples)


def test_no_target_deadlock_when_min_samples_exceeds_the_per_angle_quotas():
    """The round-robin phase. With this config the per-angle quotas alone
    cannot reach min_samples, so a target must still be offered."""
    full = {a: CFG.min_samples_per_angle for a in CFG.required_angles}
    samples = buffer(**full)
    if len(samples) >= CFG.min_samples:
        return  # phase 2 is unreachable under the shipped config
    assert not can_complete(samples)
    assert target_angle(samples) in CFG.required_angles


def test_frame_for_the_wrong_angle_is_refused_and_says_what_it_saw(
    client, session_id, scripted  # noqa: F811
):
    wrong = CFG.required_angles[1]  # anything but the opening target
    scripted.push(wrong, 42)
    r = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": sharp_jpeg_data_url(42)},
    ).json()

    assert r["accepted"] is False
    assert r["reason"] == "wrong_angle"
    # The wizard needs both halves to tell the student which way to turn.
    assert r["detected_angle"] == wrong
    assert r["target_angle"] == CFG.required_angles[0]
    assert r["captured_count"] == 0
