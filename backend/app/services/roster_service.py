"""Timetable blocks and rosters — INIT.md §9.

The one thing to get right here: contiguous periods sharing
(course, component, group, room) are ONE session, not several, and ROOM IS
PART OF THE KEY. The supplied timetable has a Wednesday case where the same
course and group run periods 3-4 in R405B and 5-6 in R407A; a merge that
ignores room silently produces wrong session boundaries (§9.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import yaml
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import Periods, settings
from app.models import Section, SectionStudent, Student, TimetableBlock

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


@dataclass(frozen=True)
class PeriodEntry:
    day: str
    period: int
    course: str
    component: str
    group: str
    room: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        # Room included deliberately — see module docstring.
        return (self.course, self.component, self.group, self.room)


@dataclass
class Block:
    day: str
    key: tuple[str, str, str, str]
    start_period: int
    end_period: int

    @property
    def course(self) -> str:
        return self.key[0]

    @property
    def component(self) -> str:
        return self.key[1]

    @property
    def group(self) -> str:
        return self.key[2]

    @property
    def room(self) -> str:
        return self.key[3]


# ───────────────────────── block merging (§9.1) ────────────────────────


def merge_blocks(day_entries: list[PeriodEntry]) -> list[Block]:
    """Merge contiguous periods sharing (course, component, group, room)."""
    blocks: list[Block] = []
    current: Block | None = None

    for e in sorted(day_entries, key=lambda x: x.period):
        if (
            current is not None
            and current.key == e.key
            and e.period == current.end_period + 1
        ):
            current.end_period = e.period  # extend
        else:
            if current is not None:
                blocks.append(current)
            current = Block(
                day=e.day, key=e.key, start_period=e.period, end_period=e.period
            )

    if current is not None:
        blocks.append(current)
    return blocks


def parse_seed(raw: dict) -> tuple[str, list[Block]]:
    """Expand seed entries to one PeriodEntry per period, then merge.

    Expanding first rather than trusting the file's period lists means the
    merge rule of §9.1 is genuinely exercised, and a seed that lists periods
    individually produces the same blocks as one that groups them.
    """
    section_code = raw["section"]
    per_day: dict[str, list[PeriodEntry]] = {d: [] for d in DAYS}

    for entry in raw["entries"]:
        for period in entry["periods"]:
            per_day.setdefault(entry["day"], []).append(
                PeriodEntry(
                    day=entry["day"],
                    period=int(period),
                    course=entry["course"],
                    component=entry["component"],
                    group=entry["group"],
                    room=entry["room"],
                )
            )

    blocks: list[Block] = []
    for day in DAYS:
        blocks.extend(merge_blocks(per_day.get(day, [])))
    return section_code, blocks


def load_seed_file(path=None) -> tuple[str, list[Block]]:
    path = path or (settings.config_dir / "timetable_seed.yaml")
    with open(path) as fh:
        return parse_seed(yaml.safe_load(fh))


def seed_timetable(db: Session, path=None) -> dict:
    """Idempotent seed load (§9.4). Re-running adds no duplicate blocks."""
    section_code, blocks = load_seed_file(path)
    section = get_or_create_section(db, section_code)

    for b in blocks:
        stmt = (
            pg_insert(TimetableBlock)
            .values(
                id=uuid.uuid4(),
                section_id=section.id,
                day_of_week=b.day,
                start_period=b.start_period,
                end_period=b.end_period,
                course_code=b.course,
                component=b.component,
                group_code=b.group,
                room=b.room,
            )
            # The unique key is (section, day, start_period); a re-seed after a
            # timetable edit must correct the rest of the row, not skip it.
            .on_conflict_do_update(
                constraint="uq_block_section_day_start",
                set_={
                    "end_period": b.end_period,
                    "course_code": b.course,
                    "component": b.component,
                    "group_code": b.group,
                    "room": b.room,
                },
            )
        )
        db.execute(stmt)
    db.commit()

    total = db.scalar(
        select(func.count())
        .select_from(TimetableBlock)
        .where(TimetableBlock.section_id == section.id)
    )
    return {"section": section_code, "blocks": int(total or 0)}


def get_or_create_section(db: Session, code: str) -> Section:
    section = db.scalar(select(Section).where(Section.code == code))
    if section is None:
        section = Section(code=code, name=code)
        db.add(section)
        db.commit()
        db.refresh(section)
    return section


# ──────────────────────── period resolution (§9.2) ─────────────────────


def block_time_window(
    start_period: int, end_period: int, on_date: date, cfg: Periods | None = None
) -> tuple[datetime, datetime]:
    """Wall-clock window for a block on a given date, in the configured tz.

    NOTE: the clock times come from config/periods.yaml, which is a §5.2
    PLACEHOLDER until a human verifies it. Attendance itself keys off period
    NUMBERS, so unverified times affect display only.
    """
    cfg = cfg or settings.periods
    tz = ZoneInfo(cfg.timezone)
    start: time = cfg.periods[start_period].start
    end: time = cfg.periods[end_period].end
    return (
        datetime.combine(on_date, start, tzinfo=tz),
        datetime.combine(on_date, end, tzinfo=tz),
    )


# ────────────────────────── eligibility (§9.3) ─────────────────────────


def assert_eligible(start_period: int, cfg: Periods | None = None) -> None:
    """Enforced at SESSION CREATION, not at finalisation (§9.3)."""
    cfg = cfg or settings.periods
    if start_period not in cfg.attendance_eligible_periods:
        raise HTTPException(
            422,
            f"Period {start_period} is not eligible for attendance recording. "
            f"Eligible periods: {cfg.attendance_eligible_periods}",
        )


def is_eligible(start_period: int, cfg: Periods | None = None) -> bool:
    cfg = cfg or settings.periods
    return start_period in cfg.attendance_eligible_periods


# ──────────────────────────────── roster ───────────────────────────────


def get_roster(db: Session, section_id: uuid.UUID) -> list[Student]:
    """The students expected in this section. Module B matches against THIS
    list and nothing wider (§1.2, §14.2)."""
    return list(
        db.scalars(
            select(Student)
            .join(SectionStudent, SectionStudent.student_id == Student.id)
            .where(SectionStudent.section_id == section_id)
            .order_by(Student.roll_no)
        )
    )
