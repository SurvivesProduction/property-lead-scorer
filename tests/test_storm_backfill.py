"""Pure-function tests for the storm-event-to-parcel matching logic --
no database, per this project's two-layer testing standard (the live
backfill script in property-lead-scorer-full has its own dry-run/real-run
verification, not unit tests against a live DB).
"""
from __future__ import annotations

from datetime import date

from extscorer.enrichment.storm_backfill import (
    StormMatch,
    compute_storm_match,
    format_storm_event_summary,
    select_nearest_storm_event,
)


def _event(event_id: str, event_date: date, event_type: str = "Hail", magnitude: str | None = "1.00") -> dict:
    return {"event_id": event_id, "event_date": event_date, "event_type": event_type, "magnitude": magnitude}


def test_selects_the_qualifying_event_for_a_parcel_with_a_clear_match() -> None:
    events = [
        _event("1", date(2010, 5, 1)),
        _event("2", date(2020, 7, 4)),  # most recent qualifying
        _event("3", date(1990, 1, 1)),  # predates year_built -- must not qualify
    ]
    result = select_nearest_storm_event(year_built=2000, storm_events=events)
    assert result["event_id"] == "2"


def test_returns_none_when_no_event_qualifies() -> None:
    events = [_event("1", date(1990, 1, 1)), _event("2", date(1995, 6, 1))]
    result = select_nearest_storm_event(year_built=2020, storm_events=events)
    assert result is None


def test_returns_none_when_year_built_is_unknown() -> None:
    # Deliberately NOT a fallback to the most significant county event --
    # see module docstring for why.
    events = [_event("1", date(2020, 7, 4), magnitude="3.00")]
    result = select_nearest_storm_event(year_built=None, storm_events=events)
    assert result is None


def test_returns_none_when_storm_events_list_is_empty() -> None:
    assert select_nearest_storm_event(year_built=2000, storm_events=[]) is None


def test_same_year_as_construction_is_treated_as_qualifying() -> None:
    # year_built has no month granularity -- same-calendar-year is treated
    # as potentially relevant, not excluded.
    events = [_event("1", date(2015, 3, 1))]
    result = select_nearest_storm_event(year_built=2015, storm_events=events)
    assert result is not None
    assert result["event_id"] == "1"


def test_ties_on_the_same_date_are_broken_deterministically_by_higher_event_id() -> None:
    events = [
        _event("100", date(2020, 6, 1)),
        _event("200", date(2020, 6, 1)),  # same date, higher event_id -- must win
        _event("150", date(2020, 6, 1)),
    ]
    result = select_nearest_storm_event(year_built=2000, storm_events=events)
    assert result["event_id"] == "200"

    # Re-run with the list in a different order -- result must not depend
    # on incidental list order (same discipline VGSI's own enumeration
    # tests hold streets/pids to).
    reordered = list(reversed(events))
    result2 = select_nearest_storm_event(year_built=2000, storm_events=reordered)
    assert result2["event_id"] == "200"


def test_selects_most_recent_over_highest_magnitude() -> None:
    # The real design decision this module documents: magnitude isn't a
    # usable ranking criterion (0% populated for Tornado in the real
    # persisted data) -- a lower-magnitude but more recent event must win
    # over an older, higher-magnitude one.
    events = [
        _event("1", date(2010, 1, 1), event_type="Hail", magnitude="4.00"),  # bigger hail, older
        _event("2", date(2023, 1, 1), event_type="Tornado", magnitude=None),  # no magnitude, more recent
    ]
    result = select_nearest_storm_event(year_built=2000, storm_events=events)
    assert result["event_id"] == "2"


def test_format_storm_event_summary_includes_magnitude_when_present() -> None:
    event = _event("1", date(2024, 5, 8), event_type="Hail", magnitude="1.50")
    summary = format_storm_event_summary(event)
    assert summary == "Hail on 2024-05-08 (magnitude 1.50)"


def test_format_storm_event_summary_omits_magnitude_when_absent() -> None:
    # The real Tornado case -- 0/6 real persisted tornado events have a
    # magnitude value.
    event = _event("1", date(2021, 7, 17), event_type="Tornado", magnitude=None)
    summary = format_storm_event_summary(event)
    assert summary == "Tornado on 2021-07-17"


def test_compute_storm_match_returns_none_for_no_qualifying_event() -> None:
    assert compute_storm_match(year_built=None, storm_events=[_event("1", date(2020, 1, 1))]) is None


def test_compute_storm_match_returns_a_populated_match() -> None:
    match = compute_storm_match(
        year_built=2000, storm_events=[_event("1", date(2020, 7, 4), event_type="Hail", magnitude="2.00")]
    )
    assert isinstance(match, StormMatch)
    assert match.event_date == date(2020, 7, 4)
    assert match.event_type == "Hail"
    assert match.summary == "Hail on 2020-07-04 (magnitude 2.00)"
