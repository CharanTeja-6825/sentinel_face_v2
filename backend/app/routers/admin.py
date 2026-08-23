"""Admin endpoints — INIT.md §10, §11.

`POST /admin/sections/{code}/students` is not in the §10 list but Module B
cannot work without a way to populate a roster, and §10 has no other endpoint
that does it. Logged in DECISIONS.md.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AttendanceDecision,
    AttendanceSession,
    FaceTemplate,
    Observation,
    Section,
    SectionStudent,
    Student,
)
from app.services.face_engine import FaceEngine
from app.services.roster_service import get_or_create_section, get_roster

router = APIRouter(prefix="/admin", tags=["admin"])


class StudentIn(BaseModel):
    roll_no: str
    name: str
    email: str | None = None


class StudentOut(BaseModel):
    id: uuid.UUID
    roll_no: str
    name: str
    email: str | None
    consent_given: bool
    template_count: int
    enrolled: bool


class RosterIn(BaseModel):
    roll_nos: list[str]


def _template_counts(db: Session) -> dict[uuid.UUID, int]:
    """Rows in face_templates per student, for the CURRENT model version.

    The version filter and the absence of an is_centroid filter both matter:
    "enrolled" has to mean exactly what gallery_service.load_roster_gallery()
    can actually match against (§14.1), otherwise /admin coverage and a
    session's enrolled_pct disagree about the same student.
    """
    rows = db.execute(
        select(FaceTemplate.student_id, func.count())
        .where(FaceTemplate.model_version == FaceEngine.MODEL_VERSION)
        .group_by(FaceTemplate.student_id)
    ).all()
    return {sid: n for sid, n in rows}


@router.get("/students", response_model=list[StudentOut])
def list_students(db: Session = Depends(get_db)):
    counts = _template_counts(db)
    students = db.scalars(select(Student).order_by(Student.roll_no)).all()
    return [
        StudentOut(
            id=s.id,
            roll_no=s.roll_no,
            name=s.name,
            email=s.email,
            consent_given=s.consent_given,
            template_count=counts.get(s.id, 0),
            enrolled=counts.get(s.id, 0) > 0,
        )
        for s in students
    ]


@router.post(
    "/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED
)
def create_student(payload: StudentIn, db: Session = Depends(get_db)):
    if db.scalar(select(Student).where(Student.roll_no == payload.roll_no)):
        raise HTTPException(409, f"Roll number {payload.roll_no!r} already exists")
    student = Student(roll_no=payload.roll_no, name=payload.name, email=payload.email)
    db.add(student)
    db.commit()
    db.refresh(student)
    return StudentOut(
        id=student.id,
        roll_no=student.roll_no,
        name=student.name,
        email=student.email,
        consent_given=student.consent_given,
        template_count=0,
        enrolled=False,
    )


@router.post("/sections/{code}/students")
def add_to_section(code: str, payload: RosterIn, db: Session = Depends(get_db)):
    section = get_or_create_section(db, code)
    added = 0
    for roll_no in payload.roll_nos:
        student = db.scalar(select(Student).where(Student.roll_no == roll_no))
        if student is None:
            raise HTTPException(404, f"Unknown roll number {roll_no!r}")
        db.execute(
            pg_insert(SectionStudent)
            .values(section_id=section.id, student_id=student.id)
            .on_conflict_do_nothing()
        )
        added += 1
    db.commit()
    return {"section": code, "roster_size": len(get_roster(db, section.id)), "added": added}


@router.get("/sections/{code}/coverage")
def coverage(code: str, db: Session = Depends(get_db)):
    """enrolled_pct and the students who still need to enrol — §10, §11."""
    section = db.scalar(select(Section).where(Section.code == code))
    if section is None:
        raise HTTPException(404, f"Unknown section {code!r}")

    roster = get_roster(db, section.id)
    counts = _template_counts(db)
    missing = [
        {"roll_no": s.roll_no, "name": s.name} for s in roster if counts.get(s.id, 0) == 0
    ]
    enrolled = len(roster) - len(missing)
    return {
        "section": code,
        "roster_size": len(roster),
        "enrolled": enrolled,
        "enrolled_pct": round(100.0 * enrolled / len(roster), 1) if roster else 0.0,
        "missing": missing,
    }


@router.get("/sessions")
def session_history(db: Session = Depends(get_db)):
    """History plus per-session auto-resolution rate — §11, §15."""
    out = []
    rows = db.scalars(
        select(AttendanceSession).order_by(AttendanceSession.created_at.desc())
    ).all()
    for s in rows:
        clusters = db.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.session_id == s.id)
        ) or 0
        auto_present = db.scalar(
            select(func.count())
            .select_from(AttendanceDecision)
            .where(
                AttendanceDecision.session_id == s.id,
                AttendanceDecision.source == "auto",
                AttendanceDecision.decision == "present",
            )
        ) or 0
        uncertain = db.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.session_id == s.id, Observation.band == "uncertain")
        ) or 0
        expected = s.expected_count or 0
        out.append(
            {
                "session_id": s.id,
                "session_date": s.session_date,
                "start_period": s.start_period,
                "status": s.status,
                "expected_count": expected,
                "detected_count": s.detected_count,
                "clusters": clusters,
                "uncertain": uncertain,
                "processing_ms": s.processing_ms,
                # Proportion of the roster decided without human attention (§15).
                "auto_resolution_rate": (
                    round((expected - uncertain) / expected, 3) if expected else None
                ),
                "auto_present": auto_present,
            }
        )
    return out
