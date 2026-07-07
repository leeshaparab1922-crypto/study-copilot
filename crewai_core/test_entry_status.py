"""Pytest coverage for entry_display_status()'s derivation logic — no LLM
call, pure function, same style as crews/syllabus_extractor/test_guardrails.py.

Run with: uv run pytest crewai_core/test_entry_status.py
"""

from crewai_core.entry_status import entry_display_status
from crewai_core.models.study_plan import EntryStatus

TODAY = "2026-07-15"
PAST = "2026-07-10"
FUTURE = "2026-07-20"


def test_past_not_started_is_missed():
    assert entry_display_status(PAST, EntryStatus.NOT_STARTED, today=TODAY) == "missed"


def test_past_in_progress_is_missed():
    assert entry_display_status(PAST, EntryStatus.IN_PROGRESS, today=TODAY) == "missed"


def test_past_completed_stays_completed():
    assert entry_display_status(PAST, EntryStatus.COMPLETED, today=TODAY) == "completed"


def test_today_not_started_is_not_missed():
    assert entry_display_status(TODAY, EntryStatus.NOT_STARTED, today=TODAY) == "not_started"


def test_today_in_progress_is_not_missed():
    assert entry_display_status(TODAY, EntryStatus.IN_PROGRESS, today=TODAY) == "in_progress"


def test_future_not_started_is_not_missed():
    assert entry_display_status(FUTURE, EntryStatus.NOT_STARTED, today=TODAY) == "not_started"


def test_future_completed_stays_completed():
    assert entry_display_status(FUTURE, EntryStatus.COMPLETED, today=TODAY) == "completed"


def test_defaults_to_real_wall_clock_today_when_not_given():
    # A date far in the past must read as missed even without an explicit
    # today override, proving the default (date.today()) path is exercised.
    assert entry_display_status("2000-01-01", EntryStatus.NOT_STARTED) == "missed"
