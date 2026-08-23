"""Module A acceptance criteria — INIT.md §7.7, §13.

Session lifecycle, diversity and completion are driven with a scripted engine
so all five angles can be reached deterministically without needing a
photographed volunteer. The two criteria that are genuinely about the DETECTOR
(no face / multiple faces) run against the real model over the real HTTP path.

As of D12 there are two things to script, because the enrolment path now has two
models: MediaPipe for detection/landmarks/pose, and ArcFace for the embedding only.
`ScriptedMediaPipe` supplies the first, `ScriptedEngine` the second.

Not covered here, because it needs a person: "a real person can enrol through
the browser". See README for the manual step.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest
from insightface.data import get_image

from app.config import settings
from app.models import EnrolmentSession, FaceTemplate
from app.services import enrolment_service
from app.services.mp_face import KPS_IDX, MPFace

CFG = settings.enrolment

FRONT_KPS = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32
)
# Head pose in DEGREES that produces each angle (D12). Positive yaw = the subject
# turned to their own left; positive pitch = looking down. Comfortably past the
# angle_yaw_deg / angle_pitch_deg boundaries but inside the max_*_deg gates.
POSE_DEG = {
    "front": (0.0, 0.0),
    "left": (25.0, 0.0),
    "right": (-25.0, 0.0),
    "up": (0.0, -25.0),
    "down": (0.0, 25.0),
}


def transform_for(yaw_deg: float, pitch_deg: float, roll_deg: float = 0.0) -> np.ndarray:
    """A 4x4 of the shape MediaPipe emits, for a known rotation. Mirrors the builder in
    test_mediapipe_pose.py, which pins that this decomposes back to the same angles."""
    x, y, z = np.deg2rad([pitch_deg, yaw_deg, roll_deg])
    rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = rz @ ry @ rx
    return m


# ─────────────────────────────── helpers ───────────────────────────────


def sharp_jpeg_data_url(seed: int = 0) -> str:
    rng = np.random.default_rng(seed)
    frame = np.clip(rng.integers(-40, 40, size=(400, 400, 3)) + 128, 0, 255).astype(
        np.uint8
    )
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def image_to_data_url(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def build_landmarks(width: float, x1: float, y1: float) -> np.ndarray:
    """A synthetic 478-point mesh spanning exactly `width` pixels.

    The five points at KPS_IDX get the canonical ArcFace positions so alignment is
    exercised for real; the rest fill the box so that `MPFace.width_px` — which is the
    landmark x-extent, not the detector box — measures `width`.
    """
    rng = np.random.default_rng(1234)
    pts = rng.uniform(0.2, 0.8, size=(478, 2)).astype(np.float32) * 112.0
    pts[list(KPS_IDX)] = FRONT_KPS
    # Pin the extremes so the span is exactly 112 before scaling.
    pts[0] = (0.0, 0.0)
    pts[1] = (112.0, 112.0)
    return pts * (width / 112.0) + (x1, y1)


class ScriptedMediaPipe:
    """Returns whatever the test queued, so pose and framing are controlled."""

    def __init__(self):
        self.queue: list[MPFace | None] = []

    def push(self, angle: str, x1=50.0, y1=50.0, width=120.0,
             det_score=0.95, blink=0.05, roll=0.0, n_faces=1):
        yaw, pitch = POSE_DEG[angle]
        lm = build_landmarks(width, x1, y1)
        self.queue.append(
            MPFace(
                det_score=det_score,
                bbox=(x1, y1, x1 + width, y1 + width),
                landmarks=lm,
                landmarks_norm=lm / 400.0,
                transform=transform_for(yaw, pitch, roll),
                blendshapes={"eyeBlinkLeft": blink, "eyeBlinkRight": blink},
                n_faces=n_faces,
            )
        )

    def analyse(self, bgr):
        return self.queue.pop(0) if self.queue else None


class ScriptedEngine:
    """ArcFace stand-in. Only align/embed_aligned are on the enrolment path now —
    detection moved to MediaPipe, so `detect()` is gone from this fake too."""

    MODEL_VERSION = "antelopev2/glintr100"

    def __init__(self):
        self.embeddings: list[np.ndarray] = []

    def push(self, seed: int):
        rng = np.random.default_rng(seed)
        v = rng.normal(size=512).astype(np.float32)
        self.embeddings.append(v / np.linalg.norm(v))

    def align(self, frame, kps):
        return np.zeros((112, 112, 3), np.uint8)

    def embed_aligned(self, crops):
        v = self.embeddings.pop(0) if self.embeddings else np.zeros(512, np.float32)
        return np.asarray([v], dtype=np.float32)


class Scripted:
    """One handle for both models, so tests read the way they did before."""

    def __init__(self, mp: ScriptedMediaPipe, engine: ScriptedEngine):
        self.mp, self.engine = mp, engine

    def push(self, angle: str, seed: int, **kw):
        self.mp.push(angle, **kw)
        self.engine.push(seed)

    def push_repeat(self, previous_seed: int, angle: str = "front"):
        """Queue a face whose embedding is identical to an earlier one."""
        self.push(angle, previous_seed)


@pytest.fixture
def scripted(monkeypatch):
    mp, engine = ScriptedMediaPipe(), ScriptedEngine()
    monkeypatch.setattr(enrolment_service, "get_mediapipe", lambda: mp)
    monkeypatch.setattr(enrolment_service, "get_engine", lambda: engine)
    return Scripted(mp, engine)


@pytest.fixture
def student(client):
    r = client.post(
        "/admin/students", json={"roll_no": "S67-001", "name": "Test Student"}
    )
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def session_id(client, student):
    r = client.post(
        "/enrolment/sessions", json={"roll_no": "S67-001", "consent": True}
    )
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def fill_session(client, scripted, session_id, per_angle: int) -> int:
    """Feed `per_angle` accepted frames for each required angle."""
    seed = 1000
    accepted = 0
    for angle in CFG.required_angles:
        for _ in range(per_angle):
            scripted.push(angle, seed)
            r = client.post(
                f"/enrolment/sessions/{session_id}/frames",
                json={"image": sharp_jpeg_data_url(seed), "angle_hint": angle},
            ).json()
            assert r["accepted"], (angle, r["reason"])
            assert r["detected_angle"] == angle
            accepted += 1
            seed += 1
    return accepted


# ───────────────────────── consent and lifecycle ───────────────────────


def test_enrolment_refused_without_consent(client, student):
    """§7.7 — enrolment is refused when consent_given is false."""
    r = client.post("/enrolment/sessions", json={"roll_no": "S67-001", "consent": False})
    assert r.status_code == 422
    assert "consent" in r.json()["detail"].lower()


def test_unknown_roll_number_is_404(client):
    r = client.post("/enrolment/sessions", json={"roll_no": "nope", "consent": True})
    assert r.status_code == 404


def test_expired_session_returns_410(client, db, session_id, scripted):
    """§7.7 — sessions past expires_at are rejected with HTTP 410."""
    import uuid as _uuid

    row = db.get(EnrolmentSession, _uuid.UUID(session_id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    scripted.push("front", 1)
    r = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": sharp_jpeg_data_url()},
    )
    assert r.status_code == 410


def test_abandon_discards_buffer(client, session_id, scripted):
    scripted.push("front", 1)
    client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": sharp_jpeg_data_url()},
    )
    assert client.delete(f"/enrolment/sessions/{session_id}").status_code == 204
    assert enrolment_service.read_buffer(__import__("uuid").UUID(session_id)) == []


# ───────────────────────── frame-level rejections ──────────────────────


def test_no_face_is_rejected_with_reason(client, session_id):
    """Real model, real HTTP path: a flat grey frame contains no face."""
    blank = np.full((400, 400, 3), 128, dtype=np.uint8)
    r = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": image_to_data_url(blank)},
    ).json()
    assert r["accepted"] is False
    assert r["reason"] == "no_face_detected"


def two_faces_at_webcam_scale(engine) -> np.ndarray:
    """A 720p frame holding two comparably-sized faces, built from bundled data.

    Not the group photo itself: BlazeFace short-range is a selfie model and does not see
    six small, turned faces in a 1280x886 group shot at any scale — measured. That is
    the right behaviour for this path (enrolment input is one large face filling a
    webcam frame), but it makes the group photo the wrong fixture for the guard. What
    the guard actually has to catch is a bystander standing beside the student, so that
    is what this builds.
    """
    src = get_image("t1")
    faces = sorted(engine.detect(src), key=lambda f: f.bbox[2] - f.bbox[0], reverse=True)
    assert len(faces) >= 2, "expected the bundled group photo to hold several faces"

    canvas = np.full((720, 1280, 3), 110, np.uint8)
    for slot, face in enumerate(faces[:2]):
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        pad = (x2 - x1) // 2
        crop = src[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
        crop = cv2.resize(crop, (420, 420), interpolation=cv2.INTER_CUBIC)
        canvas[150:570, 80 + slot * 700:500 + slot * 700] = crop
    return canvas


def test_multiple_faces_is_rejected_with_reason(client, session_id, engine_loaded):
    """Real model: two people in front of the camera must be refused, not guessed at.

    §7.7 — resolving this ambiguity would enrol the wrong person's face under this roll
    number, which no later step can detect or undo.
    """
    r = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": image_to_data_url(two_faces_at_webcam_scale(engine_loaded))},
    ).json()
    assert r["accepted"] is False
    assert r["reason"] == "multiple_faces"


def test_blurred_frame_is_rejected(client, session_id, scripted):
    """§7.7 — deliberately blurred input is rejected with too_blurry."""
    scripted.push("front", 1)
    blurred = cv2.GaussianBlur(
        np.clip(
            np.random.default_rng(0).integers(-40, 40, size=(400, 400, 3)) + 128, 0, 255
        ).astype(np.uint8),
        (31, 31),
        0,
    )
    r = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": image_to_data_url(blurred)},
    ).json()
    assert r["accepted"] is False and r["reason"] == "too_blurry"


def test_small_face_is_rejected(client, session_id, scripted):
    """§7.7 — a face far from the camera is rejected with face_too_small."""
    scripted.push("front", 1, width=CFG.min_samples_per_angle * 0 + 40.0)
    r = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": sharp_jpeg_data_url()},
    ).json()
    assert r["accepted"] is False and r["reason"] == "face_too_small"


def test_identical_frame_is_rejected_as_too_similar(client, session_id, scripted):
    """§7.7 — holding perfectly still eventually yields too_similar."""
    scripted.push("front", 7)
    first = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": sharp_jpeg_data_url(7)},
    ).json()
    assert first["accepted"]

    scripted.push_repeat(7)  # byte-identical embedding => cosine 1.0
    second = client.post(
        f"/enrolment/sessions/{session_id}/frames",
        json={"image": sharp_jpeg_data_url(7)},
    ).json()
    assert second["accepted"] is False and second["reason"] == "too_similar"


# ───────────────────────────── completion ──────────────────────────────


def test_completion_refused_when_an_angle_is_undersampled(
    client, session_id, scripted
):
    """§7.7 — the message must name the missing angle."""
    seed = 500
    for _ in range(CFG.min_samples):
        scripted.push("front", seed)
        client.post(
            f"/enrolment/sessions/{session_id}/frames",
            json={"image": sharp_jpeg_data_url(seed)},
        )
        seed += 1

    r = client.post(f"/enrolment/sessions/{session_id}/complete")
    assert r.status_code == 422
    detail = r.json()["detail"]
    for angle in ("left", "right", "up", "down"):
        assert angle in detail, detail


def test_can_complete_flips_only_when_requirements_met(client, session_id, scripted):
    n = fill_session(client, scripted, session_id, CFG.min_samples_per_angle)
    state = client.get(f"/enrolment/sessions/{session_id}").json()
    # Per-angle minimums are met, but min_samples may not be.
    assert state["can_complete"] == (n >= CFG.min_samples)


def test_full_enrolment_stores_templates_and_one_unit_centroid(
    client, db, session_id, scripted
):
    """§7.7 — after completion face_templates holds captured_count + 1 rows,
    exactly one has is_centroid, and its vector is unit length (+/-1e-5)."""
    import uuid as _uuid

    per_angle = max(
        CFG.min_samples_per_angle,
        -(-CFG.min_samples // len(CFG.required_angles)),  # ceil
    )
    captured = fill_session(client, scripted, session_id, per_angle)

    state = client.get(f"/enrolment/sessions/{session_id}").json()
    assert state["can_complete"] is True
    assert state["captured_count"] == captured

    r = client.post(f"/enrolment/sessions/{session_id}/complete")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored_templates"] == captured + 1

    student_id = _uuid.UUID(body["student_id"])
    rows = (
        db.query(FaceTemplate).filter(FaceTemplate.student_id == student_id).all()
    )
    assert len(rows) == captured + 1

    centroids = [t for t in rows if t.is_centroid]
    assert len(centroids) == 1
    norm = float(np.linalg.norm(np.asarray(centroids[0].embedding, dtype=np.float64)))
    assert norm == pytest.approx(1.0, abs=1e-5)

    # §14.1 — model_version recorded on every row.
    assert all(t.model_version == "antelopev2/glintr100" for t in rows)
    assert centroids[0].angle == "centroid"

    # §7.6 step 4 — the buffer is discarded on completion.
    assert enrolment_service.read_buffer(_uuid.UUID(session_id)) == []

    # A completed session cannot be reused.
    assert client.post(f"/enrolment/sessions/{session_id}/complete").status_code == 409
