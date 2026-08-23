"""Module C acceptance criteria — INIT.md §9.4."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import roster_service
from app.services.roster_service import PeriodEntry, merge_blocks


def _blocks_by_day(blocks, day):
    return sorted(
        [b for b in blocks if b.day == day], key=lambda b: b.start_period
    )


@pytest.fixture
def seed_blocks():
    _, blocks = roster_service.load_seed_file()
    return blocks


# ────────────────────────── merging (§9.1, §9.4) ───────────────────────


def test_seed_produces_exactly_18_blocks(seed_blocks):
    assert len(seed_blocks) == 18


def test_monday_periods_3_to_6_merge_into_one_block(seed_blocks):
    mon = _blocks_by_day(seed_blocks, "Mon")
    lab = [b for b in mon if b.start_period == 3][0]
    assert (lab.start_period, lab.end_period) == (3, 6)
    assert lab.course == "23IE4053A" and lab.room == "R407A"
    assert len(mon) == 3  # the 4-period lab, plus periods 12 and 16


def test_wednesday_stays_two_blocks_because_rooms_differ(seed_blocks):
    """Same course, same group, contiguous periods — but different rooms, so
    two blocks. A merge that ignores room silently produces wrong session
    boundaries (§9.1)."""
    wed = [b for b in _blocks_by_day(seed_blocks, "Wed") if b.course == "23IE4053A"]
    assert len(wed) == 2
    assert (wed[0].start_period, wed[0].end_period, wed[0].room) == (3, 4, "R405B")
    assert (wed[1].start_period, wed[1].end_period, wed[1].room) == (5, 6, "R407A")


def test_non_contiguous_periods_do_not_merge():
    entries = [
        PeriodEntry("Mon", 1, "C1", "L", "G1", "R1"),
        PeriodEntry("Mon", 3, "C1", "L", "G1", "R1"),  # gap at period 2
    ]
    assert len(merge_blocks(entries)) == 2


def test_blocks_per_day(seed_blocks):
    counts = {d: len(_blocks_by_day(seed_blocks, d)) for d in roster_service.DAYS}
    assert counts == {"Mon": 3, "Tue": 4, "Wed": 4, "Thu": 3, "Fri": 2, "Sat": 2}


# ───────────────────── period resolution (§9.2, §9.4) ──────────────────


def test_block_time_window_returns_ist_datetimes():
    start, end = roster_service.block_time_window(3, 6, date(2026, 8, 17))
    assert str(start.tzinfo) == "Asia/Kolkata"
    assert (start.hour, start.minute) == (9, 40)   # period 3 start
    assert (end.hour, end.minute) == (13, 50)      # period 6 end
    assert start.date() == date(2026, 8, 17)


# ──────────────────────── eligibility (§9.3, §9.4) ─────────────────────


@pytest.mark.parametrize("period", [12, 16])
def test_ineligible_periods_raise_422(period):
    with pytest.raises(HTTPException) as exc:
        roster_service.assert_eligible(period)
    assert exc.value.status_code == 422
    assert str(period) in exc.value.detail
    assert "Eligible periods" in exc.value.detail


@pytest.mark.parametrize("period", settings.periods.attendance_eligible_periods)
def test_eligible_periods_pass(period):
    roster_service.assert_eligible(period)


# ────────────────────────── seed loading (§9.4) ────────────────────────


def test_seed_is_idempotent(client):
    first = client.post("/timetable/seed").json()
    second = client.post("/timetable/seed").json()
    assert first["blocks"] == 18
    assert second["blocks"] == 18, "re-running the seed duplicated blocks"


def test_blocks_endpoint_filters_and_flags_eligibility(client):
    client.post("/timetable/seed")
    mon = client.get("/timetable/blocks", params={"section": "S-67", "day": "Mon"}).json()
    assert len(mon) == 3

    by_start = {b["start_period"]: b for b in mon}
    assert by_start[3]["eligible"] is True
    # Period 12 and 16 are loaded but cannot host attendance (§5.3).
    assert by_start[12]["eligible"] is False
    assert "not eligible" in by_start[12]["ineligible_reason"]


def test_blocks_endpoint_resolves_time_window(client):
    client.post("/timetable/seed")
    blocks = client.get(
        "/timetable/blocks",
        params={"section": "S-67", "day": "Mon", "on_date": "2026-08-17"},
    ).json()
    lab = [b for b in blocks if b["start_period"] == 3][0]
    assert lab["time_window"]["start"].startswith("2026-08-17T09:40")
    assert lab["time_window"]["end"].startswith("2026-08-17T13:50")
