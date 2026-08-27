"""Attendance session lifecycle and results — INIT.md §8.7, §10, §11."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

import redis
from fastapi import HTTPException, UploadFile
from rq import Queue
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AttendanceDecision,
    AttendanceSession,
    FaceTemplate,
    Observation,
    Student,
    TimetableBlock,
    Track,
    UnmatchedFace,
)
from app.services.face_engine import FaceEngine
from app.services.roster_service import assert_eligible, get_roster
from app.utils import storage

log = logging.getLogger(__name__)


def _queue() -> Queue:
    return Queue(
        settings.video_queue, connection=redis.Redis.from_url(settings.redis_url)
    )


def _enrolled_ids(db: Session, roster: list[Student]) -> set[uuid.UUID]:
    if not roster:
        return set()
    rows = db.scalars(
        select(FaceTemplate.student_id).where(
            FaceTemplate.student_id.in_([s.id for s in roster]),
            FaceTemplate.model_version == FaceEngine.MODEL_VERSION,
        )
    ).all()
    return set(rows)


# ───────────────────────────── creation ────────────────────────────────


def create_session(db: Session, block_id: uuid.UUID, session_date: date) -> dict:
    block = db.get(TimetableBlock, block_id)
    if block is None:
        raise HTTPException(404, "Timetable block not found")

    # §9.3 — enforced at creation, not at finalisation.
    assert_eligible(block.start_period)

    existing = db.scalar(
        select(AttendanceSession).where(
            AttendanceSession.section_id == block.section_id,
            AttendanceSession.session_date == session_date,
            AttendanceSession.start_period == block.start_period,
        )
    )
    if existing is not None:
        raise HTTPException(
            409,
            f"A session already exists for this block on {session_date} "
            f"(id {existing.id})",
        )

    roster = get_roster(db, block.section_id)
    if not roster:
        raise HTTPException(
            422,
            "This section has no roster. Add students before creating a session "
            "(POST /admin/sections/{code}/students).",
        )

    session = AttendanceSession(
        block_id=block.id,
        section_id=block.section_id,
        session_date=session_date,
        start_period=block.start_period,
        status="created",
        expected_count=len(roster),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    enrolled = _enrolled_ids(db, roster)
    return {
        "session_id": session.id,
        "expected_count": len(roster),
        "roster": [
            {
                "student_id": s.id,
                "roll_no": s.roll_no,
                "name": s.name,
                "enrolled": s.id in enrolled,
            }
            for s in roster
        ],
        "enrolled_pct": round(100.0 * len(enrolled) / len(roster), 1),
    }


# ─────────────────────────── video upload ──────────────────────────────


# 1 MiB per read. Large enough that the syscall overhead is irrelevant on a 2 GB
# upload, small enough that peak residency is noise.
UPLOAD_CHUNK_BYTES = 1024 * 1024


async def attach_video(
    db: Session, session_id: uuid.UUID, filename: str, upload: UploadFile
) -> dict:
    """Stream an upload to disk and queue it — §8.7.

    The size limit is enforced DURING the copy, not after it. Checking `len(data)`
    afterwards required the whole file in memory to have a length at all, which is
    what the limit was supposed to prevent: a 2 GB upload cost 2 GB of API process
    before it could be rejected for being 2 GB.
    """
    session = db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status == "finalized":
        raise HTTPException(409, "This session is finalized and cannot be re-run")

    cfg = settings.video
    max_bytes = cfg.max_upload_mb * 1024 * 1024

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ".mp4"
    path = storage.video_path(session_id, suffix)

    written = 0
    try:
        with path.open("wb") as fh:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    # Stop reading immediately; do not drain the rest of the body
                    # just to report a number we already know is over the limit.
                    raise HTTPException(
                        413,
                        f"Video exceeds the {cfg.max_upload_mb} MB limit",
                    )
                fh.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    # Duration is checked after writing because it needs a decodable file.
    from app.workers.video_pipeline import video_duration_s

    duration = video_duration_s(str(path))
    if duration > cfg.max_duration_minutes * 60:
        path.unlink(missing_ok=True)
        raise HTTPException(
            413,
            f"Video is {duration / 60:.1f} minutes; the limit is "
            f"{cfg.max_duration_minutes} minutes",
        )

    session.video_path = str(path)
    session.video_duration_s = duration
    session.status = "queued"
    session.error_message = None
    session.frames_sampled = 0
    db.commit()

    job = _queue().enqueue(
        "app.workers.video_pipeline.process_video",
        str(session_id),
        job_timeout="2h",
    )
    log.info("Queued job %s for session %s", job.id, session_id)
    return {"session_id": session_id, "status": "queued", "job_id": job.id}


# ──────────────────────────── status/results ───────────────────────────


def session_status(db: Session, session_id: uuid.UUID) -> dict:
    session = db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    expected_frames = None
    if session.video_duration_s:
        expected_frames = int(session.video_duration_s * settings.video.sample_fps)

    progress = None
    if expected_frames:
        progress = min(1.0, round((session.frames_sampled or 0) / expected_frames, 3))

    return {
        "session_id": session.id,
        "status": session.status,
        "session_date": session.session_date,
        "start_period": session.start_period,
        "expected_count": session.expected_count,
        "detected_count": session.detected_count,
        "frames_sampled": session.frames_sampled,
        "expected_frames": expected_frames,
        "progress": progress,
        "video_duration_s": session.video_duration_s,
        "processing_ms": session.processing_ms,
        "error_message": session.error_message,
        "model_version": session.model_version,
        "finalized_at": session.finalized_at,
    }


def session_results(db: Session, session_id: uuid.UUID) -> dict:
    session = db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    roster = {s.id: s for s in get_roster(db, session.section_id)}
    observations = db.scalars(
        select(Observation).where(Observation.session_id == session_id)
    ).all()
    decisions = {
        d.student_id: d
        for d in db.scalars(
            select(AttendanceDecision).where(
                AttendanceDecision.session_id == session_id
            )
        ).all()
    }
    tracks = db.scalars(select(Track).where(Track.session_id == session_id)).all()
    first_seen = {}
    for t in tracks:
        prior = first_seen.get(t.cluster_id)
        if prior is None or t.first_seen_s < prior:
            first_seen[t.cluster_id] = t.first_seen_s

    def student_brief(student_id):
        s = roster.get(student_id)
        return (
            {"student_id": s.id, "roll_no": s.roll_no, "name": s.name} if s else None
        )

    confident, uncertain = [], []
    for obs in observations:
        crops = obs.crop_paths or []
        row = {
            "cluster_id": obs.cluster_id,
            "student": student_brief(obs.top1_student_id),
            "score": obs.top1_score,
            "margin": obs.margin,
            "crop_url": storage.crop_url(crops[0] if crops else None),
            "first_seen_s": first_seen.get(obs.cluster_id),
        }
        if obs.band == "confident":
            confident.append(row)
        elif obs.band == "uncertain":
            row["runner_up"] = student_brief(obs.top2_student_id)
            row["runner_up_score"] = obs.top2_score
            uncertain.append(row)

    # Whatever the ledger says now, including manual overrides.
    present_ids = {
        sid for sid, d in decisions.items() if d.decision == "present"
    }
    absent = [
        {
            **student_brief(sid),
            "source": decisions[sid].source if sid in decisions else None,
        }
        for sid in roster
        if sid not in present_ids
    ]

    unmatched = [
        {
            "id": u.id,
            "cluster_id": u.cluster_id,
            "crop_url": storage.crop_url(u.crop_path),
            "best_score": u.best_score,
            "resolution": u.resolution,
        }
        for u in db.scalars(
            select(UnmatchedFace).where(UnmatchedFace.session_id == session_id)
        ).all()
    ]

    expected = session.expected_count or len(roster)
    # §15 — proportion of the roster decided without human attention.
    auto_resolution_rate = (
        round((expected - len(uncertain)) / expected, 3) if expected else None
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "confident": confident,
        "uncertain": uncertain,
        "absent": absent,
        "unmatched": unmatched,
        "stats": {
            "detected_count": session.detected_count,
            "expected_count": expected,
            "present_count": len(present_ids),
            "frames_sampled": session.frames_sampled,
            "processing_ms": session.processing_ms,
            "auto_resolution_rate": auto_resolution_rate,
            "model_version": session.model_version,
        },
    }


# ──────────────────────────── manual edits ─────────────────────────────


def _assert_editable(session: AttendanceSession) -> None:
    if session.status == "finalized":
        raise HTTPException(409, "This session is finalized; no further edits")


def apply_decisions(db: Session, session_id: uuid.UUID, updates: list[dict]) -> dict:
    session = db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    _assert_editable(session)

    roster_ids = {s.id for s in get_roster(db, session.section_id)}
    for update in updates:
        student_id = update["student_id"]
        if student_id not in roster_ids:
            raise HTTPException(
                422, f"Student {student_id} is not on this session's roster"
            )
        if update["decision"] not in ("present", "absent"):
            raise HTTPException(422, "decision must be 'present' or 'absent'")

        db.execute(
            pg_insert(AttendanceDecision)
            .values(
                session_id=session_id,
                student_id=student_id,
                decision=update["decision"],
                source="manual_override",
                decided_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                constraint="uq_decision_session_student",
                set_={
                    "decision": update["decision"],
                    "source": "manual_override",
                    "decided_at": datetime.now(timezone.utc),
                },
            )
        )
    db.commit()
    return {"updated": len(updates)}


def resolve_unmatched(db: Session, session_id: uuid.UUID, updates: list[dict]) -> dict:
    session = db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    _assert_editable(session)

    allowed = {"unresolved", "outsider", "unenrolled", "not_a_person"}
    for update in updates:
        if update["resolution"] not in allowed:
            raise HTTPException(422, f"resolution must be one of {sorted(allowed)}")
        rows = db.scalars(
            select(UnmatchedFace).where(
                UnmatchedFace.session_id == session_id,
                UnmatchedFace.cluster_id == update["cluster_id"],
            )
        ).all()
        for row in rows:
            row.resolution = update["resolution"]
            row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"updated": len(updates)}


def finalize(db: Session, session_id: uuid.UUID) -> dict:
    session = db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status == "finalized":
        return {"session_id": session.id, "status": "finalized"}
    if session.status != "completed":
        raise HTTPException(
            409, f"Cannot finalize a session with status {session.status!r}"
        )

    session.status = "finalized"
    session.finalized_at = datetime.now(timezone.utc)
    db.commit()

    present = db.scalar(
        select(func.count())
        .select_from(AttendanceDecision)
        .where(
            AttendanceDecision.session_id == session_id,
            AttendanceDecision.decision == "present",
        )
    )
    return {
        "session_id": session.id,
        "status": "finalized",
        "present": int(present or 0),
        "expected": session.expected_count,
    }
