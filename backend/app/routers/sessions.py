"""Attendance session endpoints — INIT.md §10."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionIn(BaseModel):
    block_id: uuid.UUID
    session_date: date


class DecisionIn(BaseModel):
    student_id: uuid.UUID
    decision: str  # present|absent


class UnmatchedIn(BaseModel):
    cluster_id: int
    resolution: str  # unresolved|outsider|unenrolled|not_a_person


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(payload: CreateSessionIn, db: Session = Depends(get_db)):
    """422 when the period is not eligible for attendance (§9.3)."""
    return session_service.create_session(db, payload.block_id, payload.session_date)


@router.post("/{session_id}/video", status_code=status.HTTP_202_ACCEPTED)
async def upload_video(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # The UploadFile is passed through rather than `await file.read()`-ed here.
    # Reading it whole put up to video.max_upload_mb — currently 2 GB — in the API
    # process before anything touched disk, which is the same unbounded-buffer
    # defect as §29.8 at the ingestion end. `attach_video` streams it.
    return await session_service.attach_video(
        db, session_id, file.filename or "upload.mp4", file
    )


@router.get("/{session_id}")
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return session_service.session_status(db, session_id)


@router.get("/{session_id}/results")
def get_results(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return session_service.session_results(db, session_id)


@router.patch("/{session_id}/decisions")
def patch_decisions(
    session_id: uuid.UUID, payload: list[DecisionIn], db: Session = Depends(get_db)
):
    return session_service.apply_decisions(
        db, session_id, [p.model_dump() for p in payload]
    )


@router.patch("/{session_id}/unmatched")
def patch_unmatched(
    session_id: uuid.UUID, payload: list[UnmatchedIn], db: Session = Depends(get_db)
):
    return session_service.resolve_unmatched(
        db, session_id, [p.model_dump() for p in payload]
    )


@router.post("/{session_id}/finalize")
def finalize(session_id: uuid.UUID, db: Session = Depends(get_db)):
    """Lock the session — no further edits."""
    return session_service.finalize(db, session_id)
