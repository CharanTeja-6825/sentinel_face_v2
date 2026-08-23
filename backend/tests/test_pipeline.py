"""Module B — INIT.md §8.8, §13.

Tracker, clustering, matching and banding are tested on synthetic arrays: these
are algorithms with exact expected behaviour, and testing them on real footage
would test the model instead of the logic.

The end-to-end criteria that genuinely need a camera ("one person walking in
and out produces ONE cluster") are written against tests/assets/classroom.mp4
and SKIP until that file exists. They never pass vacuously and never report a
fabricated accuracy figure (§15).
"""

from __future__ import annotations

import uuid
from datetime import date

import cv2
import numpy as np
import pytest

from app.config import settings
from app.models import (
    AttendanceDecision,
    AttendanceSession,
    Observation,
    UnmatchedFace,
)
from app.services import gallery_service
from app.services.gallery_service import band, match_clusters_to_roster
from app.utils.tracking import Detection, IoUTracker
from app.workers import video_pipeline
from tests.conftest import require_asset

VCFG = settings.video
MCFG = settings.matching


def box(x, y, w=100, h=100):
    return np.array([x, y, x + w, y + h], dtype=np.float32)


def det(x, y, score=0.9):
    return Detection(bbox=box(x, y), kps=np.zeros((5, 2), np.float32), det_score=score)


def unit(seed: int):
    """A random unit vector. Two of these are near-orthogonal in 512-D."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=512)
    return (v / np.linalg.norm(v)).astype(np.float32)


def variant(base: np.ndarray, seed: int, cosine: float = 0.85):
    """Another view of the SAME face, at an exact cosine similarity to `base`.

    Built as cos*base + sin*(unit vector orthogonal to base) so the similarity
    is exact. Adding raw gaussian noise instead would not work: at 512
    dimensions even a small per-component sigma has norm sigma*sqrt(512), which
    swamps the signal and produces an unrelated vector.
    """
    rng = np.random.default_rng(seed)
    perp = rng.normal(size=512)
    perp -= perp.dot(base) * base
    perp /= np.linalg.norm(perp)
    v = cosine * base + np.sqrt(1.0 - cosine**2) * perp
    return (v / np.linalg.norm(v)).astype(np.float32)


# ────────────────────────── tracker (§8.4) ─────────────────────────────


def test_one_person_moving_is_one_track():
    t = IoUTracker(VCFG.track_iou_threshold, VCFG.track_max_age_frames, VCFG.track_min_hits)
    for i in range(10):
        t.update([det(100 + i * 5, 100)], timestamp_s=i * 0.5)
    tracks = t.finish()
    assert len(tracks) == 1
    assert tracks[0].hits == 10


def test_two_people_are_two_tracks():
    t = IoUTracker(VCFG.track_iou_threshold, VCFG.track_max_age_frames, VCFG.track_min_hits)
    for i in range(10):
        t.update([det(100, 100), det(600, 400)], timestamp_s=i * 0.5)
    assert len(t.finish()) == 2


def test_min_hits_filters_single_frame_artefacts():
    """Reflections, posters and motion artefacts must not become people."""
    t = IoUTracker(VCFG.track_iou_threshold, VCFG.track_max_age_frames, VCFG.track_min_hits)
    for i in range(6):
        dets = [det(100, 100)]
        if i == 3:
            dets.append(det(900, 50))  # appears once, never again
        t.update(dets, timestamp_s=i * 0.5)
    tracks = t.finish()
    assert len(tracks) == 1, "a one-frame blip was emitted as a track"


def test_track_survives_a_brief_gap_then_retires():
    t = IoUTracker(VCFG.track_iou_threshold, max_age=3, min_hits=2)
    for i in range(5):
        t.update([det(100, 100)], timestamp_s=i)
    for i in range(5, 8):          # gap shorter than max_age
        t.update([], timestamp_s=i)
    t.update([det(100, 100)], timestamp_s=8)
    assert len(t.finish()) == 1

    for i in range(9, 20):          # gap longer than max_age
        t.update([], timestamp_s=i)
    for i in range(20, 23):         # a fresh appearance, min_hits detections
        t.update([det(100, 100)], timestamp_s=i)
    assert len(t.finish()) == 2, "a track should not span a gap beyond max_age"


def test_timestamps_are_recorded_on_the_track():
    t = IoUTracker(VCFG.track_iou_threshold, VCFG.track_max_age_frames, VCFG.track_min_hits)
    for i in range(5):
        t.update([det(100, 100)], timestamp_s=i * 2.0)
    track = t.finish()[0]
    assert track.first_seen_s == 0.0 and track.last_seen_s == 8.0


# ───────────────────────── clustering (§8.2, §14.5) ────────────────────


def _summary(idx, emb):
    return video_pipeline.TrackSummary(
        track_index=idx, embedding=emb, first_seen_s=0.0, last_seen_s=1.0,
        crop_count=5, mean_quality=0.8, best_crop=np.zeros((112, 112, 3), np.uint8),
        best_quality=0.8,
    )


def test_fragmented_tracks_of_one_person_merge_into_one_cluster():
    """Tracker fragmentation must not turn one student into four intruders."""
    person = unit(1)
    fragments = [_summary(i, variant(person, 100 + i)) for i in range(4)]
    labels = video_pipeline.cluster_tracks(fragments)
    assert len(set(labels.tolist())) == 1


def test_two_distinct_people_stay_two_clusters():
    a, b = unit(1), unit(2)
    tracks = [
        _summary(0, variant(a, 10)),
        _summary(1, variant(a, 11)),
        _summary(2, variant(b, 12)),
        _summary(3, variant(b, 13)),
    ]
    labels = video_pipeline.cluster_tracks(tracks)
    assert len(set(labels.tolist())) == 2
    assert labels[0] == labels[1] and labels[2] == labels[3]
    assert labels[0] != labels[2]


def test_single_track_clusters_alone():
    assert video_pipeline.cluster_tracks([_summary(0, unit(1))]).tolist() == [0]


# ──────────────────────── matching (§8.5, §14.6) ───────────────────────


def test_no_student_is_assigned_to_two_clusters():
    """The proxy loophole: independent best-match would allow this."""
    student = unit(1)
    gallery = {uuid.uuid4(): student.reshape(1, -1), uuid.uuid4(): unit(2).reshape(1, -1)}
    # Two clusters that both look like the first student.
    clusters = np.vstack([variant(student, 10, cosine=0.95),
                          variant(student, 11, cosine=0.95)])
    results = match_clusters_to_roster(clusters, gallery)
    assigned = [r["top1_student_id"] for r in results]
    assert len(assigned) == len(set(assigned)), "a student was matched twice"


def test_score_is_max_over_templates_not_the_centroid():
    """Multi-angle enrolment exists so a side view matches a side-view
    template; averaging templates would destroy that (§8.5)."""
    side = unit(5)
    front = unit(6)
    sid = uuid.uuid4()
    gallery = {sid: np.vstack([front, side])}

    results = match_clusters_to_roster(side.reshape(1, -1), gallery)
    assert results[0]["top1_score"] == pytest.approx(1.0, abs=1e-5)

    centroid = (front + side)
    centroid /= np.linalg.norm(centroid)
    assert float(side @ centroid) < 0.95, "fixture is not discriminating"


def test_more_clusters_than_students_leaves_some_unassigned():
    gallery = {uuid.uuid4(): unit(1).reshape(1, -1)}
    clusters = np.vstack([unit(10), unit(11), unit(12)])
    results = match_clusters_to_roster(clusters, gallery)
    assert len(results) == 1


def test_empty_inputs_are_safe():
    assert match_clusters_to_roster(np.zeros((0, 512), np.float32), {}) == []


# ────────────────────────── gallery scoping (§14.2) ────────────────────


def test_gallery_is_restricted_to_the_roster(db, client):
    """Loading the full student table here silently destroys accuracy while
    producing no error, so the scoping is asserted (§8.5, DECISIONS.md D7)."""
    from app.models import FaceTemplate, Student
    from app.services.face_engine import FaceEngine

    on_roster, off_roster = [], []
    for i in range(3):
        s = Student(roll_no=f"ON-{i}", name=f"On {i}")
        db.add(s)
        on_roster.append(s)
    for i in range(5):
        s = Student(roll_no=f"OFF-{i}", name=f"Off {i}")
        db.add(s)
        off_roster.append(s)
    db.commit()

    for s in on_roster + off_roster:
        db.add(
            FaceTemplate(
                student_id=s.id, embedding=unit(hash(s.roll_no) % 1000),
                angle="front", quality_score=0.9, is_centroid=False,
                model_version=FaceEngine.MODEL_VERSION, source="enrolment",
            )
        )
    db.commit()

    gallery = gallery_service.load_roster_gallery(
        db, on_roster, FaceEngine.MODEL_VERSION
    )
    assert set(gallery) == {s.id for s in on_roster}
    assert not (set(gallery) & {s.id for s in off_roster})


def test_gallery_ignores_other_model_versions(db):
    """§14.1 — embeddings from a different model are meaningless together and
    nothing would raise, so they are filtered out in the query."""
    from app.models import FaceTemplate, Student

    s = Student(roll_no="MV-1", name="Wrong version")
    db.add(s)
    db.commit()
    db.add(
        FaceTemplate(
            student_id=s.id, embedding=unit(1), angle="front", quality_score=0.9,
            is_centroid=False, model_version="buffalo_l/w600k_r50", source="enrolment",
        )
    )
    db.commit()

    with pytest.raises(gallery_service.GalleryError):
        gallery_service.load_roster_gallery(db, [s], "antelopev2/glintr100")


# ────────────────────────── banding (§8.6, §14.7) ──────────────────────


@pytest.mark.parametrize(
    "score,margin,expected",
    [
        (MCFG.t_high, MCFG.margin_min, "confident"),
        (MCFG.t_high + 0.1, MCFG.margin_min + 0.1, "confident"),
        (MCFG.t_high, MCFG.margin_min - 0.001, "uncertain"),   # margin too thin
        (MCFG.t_high - 0.001, 0.5, "uncertain"),               # score too low
        (MCFG.t_low, 0.5, "uncertain"),
        (MCFG.t_low - 0.001, 0.5, "no_match"),
        (0.0, 0.0, "no_match"),
    ],
)
def test_banding_boundaries(score, margin, expected):
    assert band(score, margin) == expected


def test_uncertain_never_becomes_present_automatically():
    """§14.7 — inverting this error asymmetry makes the system worse than
    useless. A false absent is fixed in three seconds; a false present is
    invisible and enables proxy attendance."""
    verdict = band(MCFG.t_high, MCFG.margin_min - 0.01)
    assert verdict == "uncertain"
    assert verdict != "confident"


# ───────────────────────── sampling (§8.3, §8.8) ───────────────────────


def _write_video(path, seconds=5, fps=30, size=(320, 240)):
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size
    )
    rng = np.random.default_rng(0)
    for _ in range(seconds * fps):
        writer.write(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    writer.release()


def test_sampling_rate_matches_configured_fps(tmp_path):
    """§8.8 — sampling at 2 fps on a 5-minute video yields ~600 frames. Tested
    at 5 seconds for speed; the arithmetic is identical."""
    path = tmp_path / "clip.mp4"
    _write_video(path, seconds=5, fps=30)

    sampled = list(video_pipeline.sample_frames(str(path), sample_fps=2.0))
    assert len(sampled) == pytest.approx(10, abs=1)

    timestamps = [t for t, _ in sampled]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == pytest.approx(0.0, abs=0.01)
    # 2 fps => 0.5 s apart.
    assert timestamps[1] - timestamps[0] == pytest.approx(0.5, abs=0.05)


def test_sampling_uses_grab_for_skipped_frames(tmp_path, monkeypatch):
    """§8.8 — verify grab() is used for skipped frames rather than decoding
    everything and discarding most of it."""
    path = tmp_path / "clip.mp4"
    _write_video(path, seconds=3, fps=30)

    calls = {"grab": 0, "retrieve": 0}
    real_capture = cv2.VideoCapture

    class CountingCapture:
        """Delegates to a real capture. Subclassing cv2.VideoCapture segfaults
        in the OpenCV bindings, so wrap rather than inherit."""

        def __init__(self, *a, **kw):
            self._cap = real_capture(*a, **kw)

        def grab(self):
            calls["grab"] += 1
            return self._cap.grab()

        def retrieve(self, *a, **kw):
            calls["retrieve"] += 1
            return self._cap.retrieve(*a, **kw)

        def __getattr__(self, name):
            return getattr(self._cap, name)

    monkeypatch.setattr(cv2, "VideoCapture", CountingCapture)
    frames = list(video_pipeline.sample_frames(str(path), sample_fps=2.0))

    assert calls["grab"] > calls["retrieve"] * 5, (
        f"expected mostly grab() calls, got {calls}"
    )
    assert calls["retrieve"] == len(frames)


def test_corrupt_video_raises_a_readable_error(tmp_path):
    """§8.8 — a deliberately corrupt video must fail with a readable message."""
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"this is not a video")
    with pytest.raises(ValueError, match="Could not open video"):
        list(video_pipeline.sample_frames(str(path), sample_fps=2.0))


def test_video_duration_of_generated_clip(tmp_path):
    path = tmp_path / "clip.mp4"
    _write_video(path, seconds=4, fps=25)
    assert video_pipeline.video_duration_s(str(path)) == pytest.approx(4.0, abs=0.2)


# ───────────────────── job lifecycle and idempotency ───────────────────


@pytest.fixture
def session_with_roster(client, db):
    """A section with three enrolled students and an attendance session."""
    from app.models import FaceTemplate, Student
    from app.services.face_engine import FaceEngine

    client.post("/timetable/seed")
    roll_nos = []
    for i in range(3):
        roll = f"S67-{i:03d}"
        client.post("/admin/students", json={"roll_no": roll, "name": f"Student {i}"})
        roll_nos.append(roll)
    client.post("/admin/sections/S-67/students", json={"roll_nos": roll_nos})

    for i, roll in enumerate(roll_nos):
        student = db.query(Student).filter(Student.roll_no == roll).one()
        db.add(
            FaceTemplate(
                student_id=student.id, embedding=unit(200 + i), angle="front",
                quality_score=0.9, is_centroid=False,
                model_version=FaceEngine.MODEL_VERSION, source="enrolment",
            )
        )
    db.commit()

    blocks = client.get("/timetable/blocks", params={"section": "S-67", "day": "Mon"}).json()
    eligible = [b for b in blocks if b["eligible"]][0]
    created = client.post(
        "/sessions", json={"block_id": eligible["id"], "session_date": "2026-08-17"}
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_session_creation_reports_roster_and_coverage(session_with_roster):
    assert session_with_roster["expected_count"] == 3
    assert session_with_roster["enrolled_pct"] == 100.0
    assert all(r["enrolled"] for r in session_with_roster["roster"])


def test_creating_a_session_for_an_ineligible_period_is_422(client, db):
    """§9.4 — period 12 and 16 cannot host attendance."""
    client.post("/timetable/seed")
    client.post("/admin/students", json={"roll_no": "X-1", "name": "X"})
    client.post("/admin/sections/S-67/students", json={"roll_nos": ["X-1"]})

    blocks = client.get("/timetable/blocks", params={"section": "S-67", "day": "Mon"}).json()
    ineligible = [b for b in blocks if not b["eligible"]][0]
    r = client.post(
        "/sessions", json={"block_id": ineligible["id"], "session_date": "2026-08-17"}
    )
    assert r.status_code == 422
    assert "not eligible" in r.json()["detail"]


def test_status_endpoint_reports_lifecycle(client, session_with_roster):
    status = client.get(f"/sessions/{session_with_roster['session_id']}").json()
    assert status["status"] == "created"
    assert status["expected_count"] == 3


def test_reprocessing_replaces_rather_than_duplicates(client, db, session_with_roster):
    """§8.7 — re-running a completed job must never double-write."""
    session_id = uuid.UUID(session_with_roster["session_id"])
    session = db.get(AttendanceSession, session_id)

    # Stand in for a completed run.
    for cluster_id in (0, 1):
        db.add(
            Observation(
                session_id=session_id, cluster_id=cluster_id, band="no_match",
                crop_paths=[], model_version="antelopev2/glintr100",
            )
        )
        db.add(
            UnmatchedFace(
                session_id=session_id, cluster_id=cluster_id, crop_path="x.jpg"
            )
        )
    db.commit()
    assert db.query(Observation).filter(Observation.session_id == session_id).count() == 2

    video_pipeline.reset_session_results(session_id, db)

    assert db.query(Observation).filter(Observation.session_id == session_id).count() == 0
    assert db.query(UnmatchedFace).filter(UnmatchedFace.session_id == session_id).count() == 0


def test_manual_override_is_idempotent(client, db, session_with_roster):
    """§6 invariant 2 — repeated PATCHes update one row, never duplicate."""
    session_id = session_with_roster["session_id"]
    student_id = session_with_roster["roster"][0]["student_id"]

    for _ in range(3):
        r = client.patch(
            f"/sessions/{session_id}/decisions",
            json=[{"student_id": student_id, "decision": "present"}],
        )
        assert r.status_code == 200

    rows = (
        db.query(AttendanceDecision)
        .filter(
            AttendanceDecision.session_id == uuid.UUID(session_id),
            AttendanceDecision.student_id == uuid.UUID(student_id),
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].decision == "present"
    assert rows[0].source == "manual_override"


def test_override_rejects_students_off_the_roster(client, session_with_roster):
    r = client.patch(
        f"/sessions/{session_with_roster['session_id']}/decisions",
        json=[{"student_id": str(uuid.uuid4()), "decision": "present"}],
    )
    assert r.status_code == 422


def test_finalize_locks_the_session(client, db, session_with_roster):
    session_id = session_with_roster["session_id"]
    session = db.get(AttendanceSession, uuid.UUID(session_id))
    session.status = "completed"
    db.commit()

    assert client.post(f"/sessions/{session_id}/finalize").json()["status"] == "finalized"
    # No further edits once locked.
    r = client.patch(
        f"/sessions/{session_id}/decisions",
        json=[{"student_id": session_with_roster["roster"][0]["student_id"],
               "decision": "absent"}],
    )
    assert r.status_code == 409


def test_absent_students_are_reported(client, db, session_with_roster):
    """§8.8 — a student enrolled but absent from the video is marked absent."""
    session_id = uuid.UUID(session_with_roster["session_id"])
    for row in session_with_roster["roster"]:
        db.add(
            AttendanceDecision(
                session_id=session_id, student_id=uuid.UUID(row["student_id"]),
                decision="absent", source="auto",
            )
        )
    db.commit()

    results = client.get(f"/sessions/{session_id}/results").json()
    assert len(results["absent"]) == 3
    assert results["stats"]["present_count"] == 0


# ──────────────── end-to-end, pending real footage (§13) ───────────────


@pytest.mark.parametrize("criterion", ["one_cluster_per_person", "roster_assignment"])
def test_end_to_end_on_real_footage(criterion, client, db, session_with_roster):
    """§8.8 end-to-end criteria. Skips until real footage is supplied — see
    tests/assets/README.md. It must never pass vacuously."""
    require_asset("classroom.mp4")
    pytest.fail(
        "Footage is present but the end-to-end assertions have not been wired "
        "to it yet — see tests/assets/README.md"
    )
