"""Timetable endpoints — INIT.md §10."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Section, TimetableBlock
from app.schemas.timetable import BlockOut, SeedResult
from app.services import roster_service

router = APIRouter(prefix="/timetable", tags=["timetable"])


def _to_out(block: TimetableBlock, section_code: str, on: date | None = None) -> BlockOut:
    window = None
    if on is not None:
        start, end = roster_service.block_time_window(
            block.start_period, block.end_period, on
        )
        window = {"start": start.isoformat(), "end": end.isoformat()}
    return BlockOut(
        id=block.id,
        section=section_code,
        day_of_week=block.day_of_week,
        start_period=block.start_period,
        end_period=block.end_period,
        course_code=block.course_code,
        component=block.component,
        group_code=block.group_code,
        room=block.room,
        eligible=roster_service.is_eligible(block.start_period),
        # Shown greyed WITH the reason, not hidden — §11.
        ineligible_reason=(
            None
            if roster_service.is_eligible(block.start_period)
            else f"Period {block.start_period} is not eligible for attendance recording"
        ),
        time_window=window,
    )


@router.post("/seed", response_model=SeedResult)
def seed(db: Session = Depends(get_db)) -> SeedResult:
    """Load config/timetable_seed.yaml. Idempotent — §9.4."""
    result = roster_service.seed_timetable(db)
    return SeedResult(**result)


@router.get("/blocks", response_model=list[BlockOut])
def list_blocks(
    section: str | None = Query(None),
    day: str | None = Query(None),
    on_date: date | None = Query(None, description="resolve clock times for this date"),
    db: Session = Depends(get_db),
) -> list[BlockOut]:
    stmt = select(TimetableBlock, Section.code).join(
        Section, Section.id == TimetableBlock.section_id
    )
    if section:
        stmt = stmt.where(Section.code == section)
    if day:
        stmt = stmt.where(TimetableBlock.day_of_week == day)
    stmt = stmt.order_by(TimetableBlock.day_of_week, TimetableBlock.start_period)

    return [_to_out(b, code, on_date) for b, code in db.execute(stmt).all()]


@router.get("/blocks/{block_id}", response_model=BlockOut)
def get_block(
    block_id: uuid.UUID,
    on_date: date | None = Query(None),
    db: Session = Depends(get_db),
) -> BlockOut:
    row = db.execute(
        select(TimetableBlock, Section.code)
        .join(Section, Section.id == TimetableBlock.section_id)
        .where(TimetableBlock.id == block_id)
    ).first()
    if row is None:
        raise HTTPException(404, "Block not found")
    block, code = row
    return _to_out(block, code, on_date)
