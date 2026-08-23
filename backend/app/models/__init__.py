"""ORM models — INIT.md §6. Import from here so Alembic autogenerate and
`Base.metadata` see every table."""

from app.models.observation import (
    AttendanceDecision,
    Observation,
    Track,
    UnmatchedFace,
)
from app.models.section import Section, TimetableBlock
from app.models.session import AttendanceSession
from app.models.student import SectionStudent, Student
from app.models.template import EnrolmentSession, FaceTemplate

__all__ = [
    "AttendanceDecision",
    "AttendanceSession",
    "EnrolmentSession",
    "FaceTemplate",
    "Observation",
    "Section",
    "SectionStudent",
    "Student",
    "TimetableBlock",
    "Track",
    "UnmatchedFace",
]
