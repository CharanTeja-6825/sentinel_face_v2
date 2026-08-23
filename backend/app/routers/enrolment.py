"""Enrolment endpoints — INIT.md §10."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.enrolment import (
    CompleteOut,
    CreateSessionIn,
    CreateSessionOut,
    FrameIn,
    FrameOut,
    SessionStateOut,
)
from app.services import enrolment_service

router = APIRouter(prefix="/enrolment", tags=["enrolment"])


@router.post(
    "/sessions", response_model=CreateSessionOut, status_code=status.HTTP_201_CREATED
)
def create_session(payload: CreateSessionIn, db: Session = Depends(get_db)):
    session = enrolment_service.create_session(db, payload.roll_no, payload.consent)
    cfg = settings.enrolment
    return CreateSessionOut(
        session_id=session.id,
        student_id=session.student_id,
        required_angles=cfg.required_angles,
        min_samples=cfg.min_samples,
        min_samples_per_angle=cfg.min_samples_per_angle,
        # A new session has an empty buffer, so this is the first required
        # angle — derived rather than assumed, so it stays right if the
        # ordering rule in target_angle() ever changes.
        target_angle=enrolment_service.target_angle([]),
        expires_at=session.expires_at,
    )


@router.post("/sessions/{session_id}/frames", response_model=FrameOut)
def submit_frame(session_id: uuid.UUID, payload: FrameIn, db: Session = Depends(get_db)):
    return enrolment_service.submit_frame(db, session_id, payload.image)


@router.post("/sessions/{session_id}/complete", response_model=CompleteOut)
def complete(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return enrolment_service.complete_session(db, session_id)


@router.get("/sessions/{session_id}", response_model=SessionStateOut)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return enrolment_service.session_state(db, session_id)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def abandon(session_id: uuid.UUID, db: Session = Depends(get_db)):
    enrolment_service.abandon_session(db, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
