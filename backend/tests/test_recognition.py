"""Live Test — single-frame identification (recognition_service).

The engine is faked. What is under test is the wiring: that a frame reaches the
roster-scoped gallery, that the verdict comes from the same banding the video
pipeline uses, and that a rejected face is still reported with its reason rather
than silently disappearing.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import HTTPException

from app.models import FaceTemplate, SectionStudent, Student
from app.services import quality, recognition_service, roster_service
from app.services.face_engine import FaceEngine
from app.services.quality import QualityResult
from app.utils.tracking import Detection
from app.workers import video_pipeline
from tests.test_pipeline import unit

SECTION = "T-1"


def data_url() -> str:
    """A real, decodable frame — decode_data_url is not mocked."""
    frame = np.full((720, 1280, 3), 128, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def detection() -> Detection:
    return Detection(
        bbox=np.array([500, 200, 700, 460], dtype=np.float32),
        kps=np.zeros((5, 2), np.float32),
        det_score=0.95,
    )


@pytest.fixture
def enrolled(db):
    """Two students on section T-1, one template each, at known embeddings."""
    section = roster_service.get_or_create_section(db, SECTION)
    students = [Student(roll_no="T-1-A", name="Ada"), Student(roll_no="T-1-B", name="Bo")]
    db.add_all(students)
    db.commit()
    for i, s in enumerate(students, start=1):
        db.add(SectionStudent(section_id=section.id, student_id=s.id))
        db.add(
            FaceTemplate(
                student_id=s.id, embedding=unit(i), angle="front", quality_score=0.9,
                is_centroid=False, model_version=FaceEngine.MODEL_VERSION,
                source="enrolment",
            )
        )
    db.commit()
    return students


def wire(monkeypatch, embedding: np.ndarray, accepted: bool = True):
    """Fake the detector, the gate and the engine; leave everything else real."""
    monkeypatch.setattr(video_pipeline, "detect_frame", lambda engine, frame: [detection()])
    monkeypatch.setattr(
        quality,
        "assess",
        lambda det, frame, cfg=None: QualityResult(
            accepted=accepted,
            reason=None if accepted else quality.TOO_SMALL,
            quality_score=0.81 if accepted else 0.1,
        ),
    )
    engine = SimpleNamespace(
        align=lambda frame, kps: np.zeros((112, 112, 3), np.uint8),
        embed_aligned=lambda crops: np.vstack([embedding] * len(crops)),
    )
    monkeypatch.setattr(recognition_service, "get_engine", lambda: engine)


def test_an_enrolled_face_is_named_confidently(db, enrolled, monkeypatch):
    wire(monkeypatch, unit(1))
    out = recognition_service.identify_frame(db, data_url(), SECTION)

    (face,) = out["faces"]
    assert face["accepted"]
    assert face["roll_no"] == "T-1-A"
    assert face["name"] == "Ada"
    assert face["band"] == "confident"
    assert face["score"] == pytest.approx(1.0, abs=1e-3)
    assert out["gallery_size"] == 2 and out["roster_size"] == 2
    # The screen shows the arithmetic, so the numbers behind it must travel.
    assert out["thresholds"]["t_high"] > out["thresholds"]["t_low"]


def test_a_stranger_is_no_match_and_is_not_named(db, enrolled, monkeypatch):
    """A no_match still has a top-1. Reporting its name would invite reading a
    rejected guess as an answer."""
    wire(monkeypatch, unit(999))
    out = recognition_service.identify_frame(db, data_url(), SECTION)

    (face,) = out["faces"]
    assert face["band"] == "no_match"
    assert face["roll_no"] is None and face["name"] is None
    assert face["score"] < out["thresholds"]["t_low"]


def test_a_gated_face_is_still_reported_with_its_reason(db, enrolled, monkeypatch):
    """Going blank tells the user nothing; `face_too_small` tells them to move."""
    wire(monkeypatch, unit(1), accepted=False)
    out = recognition_service.identify_frame(db, data_url(), SECTION)

    (face,) = out["faces"]
    assert face["accepted"] is False
    assert face["reason"] == quality.TOO_SMALL
    assert face["band"] is None and face["score"] is None


def test_unknown_section_is_404_not_a_silent_empty_gallery(db):
    with pytest.raises(HTTPException) as exc:
        recognition_service.identify_frame(db, data_url(), "NOPE")
    assert exc.value.status_code == 404


def test_nothing_is_written(db, enrolled, monkeypatch):
    """The Live Test must never mark attendance. See the module docstring."""
    from app.models import AttendanceDecision, AttendanceSession, Observation

    wire(monkeypatch, unit(1))
    recognition_service.identify_frame(db, data_url(), SECTION)

    for model in (AttendanceSession, AttendanceDecision, Observation):
        assert db.query(model).count() == 0
    assert db.query(FaceTemplate).count() == 2      # unchanged
