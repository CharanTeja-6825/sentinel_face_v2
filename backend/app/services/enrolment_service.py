"""Module A — registration — INIT.md §7.

GUIDED capture, not opportunistic. The session has exactly one TARGET ANGLE at
any moment, derived from the buffer by `target_angle()`, and a frame is banked
only if its detected pose matches that target. The wizard walks the student
through `required_angles` in order — front, then left, then right, then up,
then down — and cannot skip ahead by accident. Without this the wizard sprays
frames at ~700 ms and banks whichever angle happens to come out of the pose
classifier, so a student looking straight ahead fills the whole `front` quota
in seconds while the prompt is already asking for something else. The gallery
that results is deep in one orientation and thin in the other four, which is
exactly the shape §8.5 max-over-templates matching cannot use.

Two further gates exist only on this path, because enrolment templates are
matched against for the rest of the term and a weak one is permanent:
`min_quality_score` (a floor on `weighted_score()`) and a tightened
`diversity_max_cosine`.

Accepted frames accumulate in a Redis-backed session buffer until /complete,
at which point they become face_templates rows plus one centroid. The buffer is
discarded on completion (§7.6 step 4). See DECISIONS.md D6 for why Redis.

The front of this pipeline is MediaPipe as of D12: preprocessing, then Face Detector
plus Face Landmarker for detection, 478 landmarks, real 3D pose in degrees and
blendshapes. ArcFace is still the recogniser — MediaPipe has no identity model, and
face-mesh geometry varies more with pose and expression than it does between people —
but it now embeds a crop that MediaPipe aligned, using iris centres rather than SCRFD's
estimate of where the eyes are. SCRFD does not run on this path at all any more.

The guided-capture state machine below (`target_angle`, the buffer, the diversity check,
consent, expiry) is untouched by that: D11 is a statement about which orientation to ask
for next, and it does not care how the orientation was measured.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import redis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EnrolmentSession, FaceTemplate, Student
from app.services import preprocess, quality
from app.services.face_engine import FaceEngine, get_engine
from app.services.mp_face import LANDMARK_SOURCE, get_mediapipe

log = logging.getLogger(__name__)

_redis: redis.Redis | None = None


def _r() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url)
    return _redis


def _key(session_id: uuid.UUID) -> str:
    return f"enrol:{session_id}"


@dataclass
class BufferedSample:
    embedding: list[float]
    angle: str
    quality_score: float
    # Degrees, from MediaPipe (D12). Defaulted so a buffer written by the previous
    # build is still readable after a deploy mid-enrolment — the Redis key outlives the
    # process by up to session_timeout_minutes.
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0


# ─────────────────────────── session buffer ────────────────────────────


def read_buffer(session_id: uuid.UUID) -> list[BufferedSample]:
    raw = _r().get(_key(session_id))
    if not raw:
        return []
    return [BufferedSample(**s) for s in json.loads(raw)]


def write_buffer(session_id: uuid.UUID, samples: list[BufferedSample]) -> None:
    _r().set(
        _key(session_id),
        json.dumps([asdict(s) for s in samples]),
        ex=settings.enrolment.session_timeout_minutes * 60,
    )


def drop_buffer(session_id: uuid.UUID) -> None:
    _r().delete(_key(session_id))


# ────────────────────────── session lifecycle ──────────────────────────


def create_session(db: Session, roll_no: str, consent: bool) -> EnrolmentSession:
    # §7.7 — enrolment is refused when consent is not given.
    if not consent:
        raise HTTPException(
            422,
            "Consent is required before any face data can be captured. "
            "No images or embeddings are stored without it.",
        )

    student = db.scalar(select(Student).where(Student.roll_no == roll_no))
    if student is None:
        raise HTTPException(
            404,
            f"Unknown roll number {roll_no!r}. Create the student first "
            "(POST /admin/students).",
        )

    student.consent_given = True
    student.consent_at = datetime.now(timezone.utc)

    session = EnrolmentSession(
        student_id=student.id,
        status="active",
        captured_count=0,
        angles_captured={},
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.enrolment.session_timeout_minutes),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_active_session(db: Session, session_id: uuid.UUID) -> EnrolmentSession:
    session = db.get(EnrolmentSession, session_id)
    if session is None:
        raise HTTPException(404, "Enrolment session not found")

    if session.status == "completed":
        raise HTTPException(409, "This enrolment session is already complete")
    if session.status in ("expired", "abandoned"):
        raise HTTPException(410, f"This enrolment session was {session.status}")

    # §7.7 — sessions past expires_at are rejected with HTTP 410.
    if session.expires_at <= datetime.now(timezone.utc):
        session.status = "expired"
        db.commit()
        drop_buffer(session_id)
        raise HTTPException(
            410,
            "This enrolment session has expired. Start a new one.",
        )
    return session


def abandon_session(db: Session, session_id: uuid.UUID) -> None:
    session = db.get(EnrolmentSession, session_id)
    if session is None:
        raise HTTPException(404, "Enrolment session not found")
    if session.status == "active":
        session.status = "abandoned"
        db.commit()
    drop_buffer(session_id)


# ───────────────────────────── frame intake ────────────────────────────


def decode_data_url(image: str) -> np.ndarray:
    """Decode a `data:image/jpeg;base64,...` payload to a BGR frame."""
    payload = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        buf = np.frombuffer(base64.b64decode(payload, validate=True), dtype=np.uint8)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, f"Malformed image payload: {exc}") from None
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Image payload could not be decoded")
    return frame


def angle_progress(samples: list[BufferedSample]) -> dict[str, int]:
    progress = {a: 0 for a in settings.enrolment.required_angles}
    for s in samples:
        progress[s.angle] = progress.get(s.angle, 0) + 1
    return progress


def missing_angles(samples: list[BufferedSample]) -> list[str]:
    cfg = settings.enrolment
    progress = angle_progress(samples)
    return [
        a for a in cfg.required_angles if progress.get(a, 0) < cfg.min_samples_per_angle
    ]


def can_complete(samples: list[BufferedSample]) -> bool:
    return (
        len(samples) >= settings.enrolment.min_samples and not missing_angles(samples)
    )


def target_angle(samples: list[BufferedSample]) -> str | None:
    """The one orientation this session is asking for right now, or None.

    Derived from the buffer, so it needs no stored state of its own and cannot
    drift out of step with what was actually captured (a client that reloads
    mid-enrolment resumes on the same angle).

    Phase 1 is §7.1's flow: the first angle in `required_angles` order still
    short of `min_samples_per_angle`. Finish an angle before moving on.

    Phase 2 only runs when `min_samples` exceeds
    `min_samples_per_angle * len(required_angles)` — a config the operator is
    free to set. Without it the target would be None while `can_complete()`
    was still False and the session would deadlock: no angle wants a frame,
    but the total is not met. Instead it round-robins the least-sampled angle,
    which keeps the guidance on and balances the gallery.
    """
    if can_complete(samples):
        return None
    cfg = settings.enrolment
    progress = angle_progress(samples)
    for angle in cfg.required_angles:
        if progress.get(angle, 0) < cfg.min_samples_per_angle:
            return angle
    # min() returns the FIRST minimum, so required_angles order breaks ties.
    return min(cfg.required_angles, key=lambda a: progress.get(a, 0))


def submit_frame(db: Session, session_id: uuid.UUID, image: str) -> dict:
    """preprocess -> MediaPipe -> quality gate -> align -> embed -> diversity -> buffer.

    §7.1, rewired for D12/D13. Returns the §10 response shape.

    The two-copy structure is the whole point of D13. Detection, landmarking and pose
    read an ENHANCED, downscaled copy, so a dim or backlit frame is still findable.
    Alignment and embedding read the ORIGINAL full-resolution pixels, so the vectors
    that land in the gallery do not depend on the preprocessing parameters and cannot be
    invalidated by retuning them.
    """
    session = get_active_session(db, session_id)
    cfg = settings.enrolment
    samples = read_buffer(session_id)

    def response(accepted: bool, reason: str | None, result=None, extra=None) -> dict:
        body = {
            "accepted": accepted,
            "reason": reason,
            "detected_angle": result.angle if result else None,
            "quality_score": result.quality_score if result else 0.0,
            "captured_count": len(samples),
            "angle_progress": angle_progress(samples),
            "can_complete": can_complete(samples),
            # The wizard renders the prompt from this, rather than working out
            # the stage itself — one authority for which way to turn.
            "target_angle": target_angle(samples),
            "min_samples_per_angle": cfg.min_samples_per_angle,
            "pose": None,
            "landmarks": None,
            "eyes_open": None,
        }
        if result is not None and result.pose_in_degrees:
            body["pose"] = {
                "yaw": round(result.yaw, 1),
                "pitch": round(result.pitch, 1),
                "roll": round(result.roll, 1),
            }
        body.update(extra or {})
        return body

    if len(samples) >= cfg.max_samples:
        return response(False, "max_samples_reached")

    frame = decode_data_url(image)

    # D13 — enhance a downscaled copy for detection only. `scale` maps a coordinate in
    # the small image back to the original, which is how the landmarks return to
    # full-resolution space below.
    small, scale = preprocess.fit_to_max_side(frame, settings.preprocess.max_side)
    enhanced, enhancement = preprocess.enhance(small)

    mp_face = get_mediapipe().analyse(enhanced)
    if mp_face is None:
        return response(False, quality.NO_FACE)
    if mp_face.n_faces > 1:
        # Ambiguity here would enrol the wrong person's face under this roll
        # number, so refuse rather than guess (§7.7).
        return response(False, quality.MULTIPLE_FACES)

    # Back to full-resolution coordinates before anything touches the raw frame.
    if scale != 1.0:
        mp_face.landmarks = mp_face.landmarks / scale
        mp_face.bbox = tuple(v / scale for v in mp_face.bbox)

    result = quality.assess_mediapipe(mp_face, frame)
    overlay = mp_face.overlay()
    eyes_open = mp_face.eye_blink <= settings.quality.max_eye_blink
    extra = {"landmarks": overlay, "eyes_open": eyes_open}

    if not result.accepted:
        return response(False, result.reason, result, extra)

    # Guided capture: bank this frame only for the angle being asked for.
    # Reported with the angle we DID see, so the wizard can say "you are facing
    # front, turn to your left" instead of failing silently.
    target = target_angle(samples)
    if target is not None and result.angle != target:
        return response(False, quality.WRONG_ANGLE, result, extra)

    # Enrolment-only floor. The §7.3 gate says "usable"; a template that gets
    # matched against for the rest of the term should be better than usable,
    # and here — unlike the video path — we can simply ask for another frame.
    if result.quality_score < cfg.min_quality_score:
        return response(False, quality.LOW_QUALITY, result, extra)

    # Align on MediaPipe's iris centres, embed the RAW pixels. Both are existing
    # FaceEngine methods — the video path has used them since Phase 5.
    engine = get_engine()
    crop = engine.align(frame, mp_face.arcface_kps())
    embedding = engine.embed_aligned([crop])[0]

    # §7.5 — reject frames nearly identical to ones already captured.
    for existing in samples:
        if float(np.dot(embedding, np.asarray(existing.embedding, dtype=np.float32))) > (
            cfg.diversity_max_cosine
        ):
            return response(False, quality.TOO_SIMILAR, result, extra)

    samples.append(
        BufferedSample(
            embedding=[float(v) for v in embedding],
            angle=result.angle,
            quality_score=result.quality_score,
            yaw=result.yaw,
            pitch=result.pitch,
            roll=result.roll,
        )
    )
    write_buffer(session_id, samples)

    session.captured_count = len(samples)
    session.angles_captured = angle_progress(samples)
    db.commit()

    if enhancement.get("gamma", 1.0) != 1.0:
        log.debug(
            "enrolment frame enhanced: gamma=%.2f luma %.2f -> %.2f",
            enhancement["gamma"],
            enhancement["mean_luma_before"],
            enhancement["mean_luma_after"],
        )

    return response(True, None, result, extra)


# ──────────────────────────── completion (§7.6) ────────────────────────


def complete_session(db: Session, session_id: uuid.UUID) -> dict:
    session = get_active_session(db, session_id)
    cfg = settings.enrolment
    samples = read_buffer(session_id)

    # Name the specific shortfall — §7.7, §10. Both branches list the angles still
    # short, because under guided capture the count is almost never the whole story:
    # the total falls short precisely BECAUSE some angles were never reached, and a
    # bare "need 15, have 3" leaves the student with nothing to act on.
    progress = angle_progress(samples)
    missing = missing_angles(samples)
    shortfall = ", ".join(
        f"{a} {progress.get(a, 0)}/{cfg.min_samples_per_angle}" for a in missing
    )

    if len(samples) < cfg.min_samples:
        detail = f"Need at least {cfg.min_samples} samples, have {len(samples)}."
        if missing:
            detail += f" Still short: {shortfall}."
        raise HTTPException(422, detail)
    if missing:
        raise HTTPException(422, f"Under-sampled angles: {shortfall}")

    vectors = np.asarray([s.embedding for s in samples], dtype=np.float32)

    for sample, vec in zip(samples, vectors):
        db.add(
            FaceTemplate(
                student_id=session.student_id,
                embedding=vec,
                angle=sample.angle,
                quality_score=sample.quality_score,
                is_centroid=False,
                # Still the RECOGNISER's version, and deliberately unchanged by D12 —
                # glintr100 has not moved, only the landmarks feeding its alignment.
                # Bumping it would orphan every existing template with no backfill path.
                model_version=FaceEngine.MODEL_VERSION,
                landmark_source=LANDMARK_SOURCE,
                yaw_deg=sample.yaw,
                pitch_deg=sample.pitch,
                roll_deg=sample.roll,
                source="enrolment",
            )
        )

    # One centroid: mean of all embeddings, re-normalised to unit length.
    centroid = vectors.mean(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-12)
    db.add(
        FaceTemplate(
            student_id=session.student_id,
            embedding=centroid.astype(np.float32),
            angle="centroid",
            quality_score=float(np.mean([s.quality_score for s in samples])),
            is_centroid=True,
            model_version=FaceEngine.MODEL_VERSION,
            landmark_source=LANDMARK_SOURCE,
            # No pose: the centroid is the mean of five orientations, which is not
            # itself an orientation. NULL says that; 0.0 would claim it faces front.
            source="enrolment",
        )
    )

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    session.captured_count = len(samples)
    session.angles_captured = angle_progress(samples)
    db.commit()

    drop_buffer(session_id)

    return {
        "student_id": session.student_id,
        "stored_templates": len(samples) + 1,
        "angles": angle_progress(samples),
    }


def session_state(db: Session, session_id: uuid.UUID) -> dict:
    session = db.get(EnrolmentSession, session_id)
    if session is None:
        raise HTTPException(404, "Enrolment session not found")
    samples = read_buffer(session_id)
    return {
        "session_id": session.id,
        "student_id": session.student_id,
        "status": session.status,
        "captured_count": len(samples),
        "angle_progress": angle_progress(samples),
        "can_complete": can_complete(samples),
        "target_angle": target_angle(samples),
        "expires_at": session.expires_at,
        "required_angles": settings.enrolment.required_angles,
        "min_samples": settings.enrolment.min_samples,
        "min_samples_per_angle": settings.enrolment.min_samples_per_angle,
    }
