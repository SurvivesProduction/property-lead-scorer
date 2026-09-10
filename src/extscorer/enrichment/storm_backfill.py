"""Generic, client-agnostic logic for matching one parcel to its
temporally-nearest relevant `storm_events` row.

Nothing in this module encodes any client-specific business logic, per the
same public/full split `extscorer.scoring.basic` follows -- a downstream
deployment's own backfill script (e.g. `property-lead-scorer-full/scripts/
backfill_storm_events_on_parcels.py`) is what actually reads/writes the
live database; everything here is a pure function over plain dicts so it's
unit-testable without one.

## Design decision (resolved against real persisted data, not assumed)

`storm_events` is county-level, not per-address -- there is no real
spatial "nearest" to compute for this data (no lat/lon on a storm event).
`nearest_storm_event_date` is about TEMPORAL relevance: of the storm
events that could plausibly have affected a given parcel's structure,
which one is most recent.

**Qualification**: an event qualifies for a parcel if `event_date`'s year
is `>= year_built` -- `year_built` is assessor completion-year
granularity (no month), so a storm later in the same calendar year is
treated as potentially relevant rather than excluded on a precision this
data doesn't actually have.

**Selection: most recent qualifying event, NOT highest-magnitude.**
Checked directly against the real persisted `storm_events` data before
deciding: `Tornado` events have `magnitude` populated 0% of the time
(NOAA scores tornado severity via a separate `TOR_F_SCALE` field, not
`MAGNITUDE`), while `Hail`/`Thunderstorm Wind` are 100% populated but on
different, non-comparable scales (hail diameter in inches vs. wind speed).
A magnitude-based ranking would systematically misrank or entirely exclude
tornadoes -- the single most severe event type -- so "most recent" is the
only criterion that applies uniformly across every event type this data
actually contains.

**Unknown `year_built`** (vacant land, outbuildings-only parcels): returns
`None` -- deliberately NOT a fallback to the county's most significant
event. `extscorer.scoring.basic` already excludes a parcel with no known
year_built from lead-candidacy entirely; fabricating a storm date for a
parcel that was never a scoring candidate would misleadingly suggest
storm relevance where none exists. The same reasoning applies to a parcel
whose real `year_built` postdates every event on file (e.g. built after
the most recent storm) -- also `None`, a genuine "no qualifying event
exists yet" state, not an error.

**Ties** (two events sharing the same `event_date`) are broken by the
higher `event_id` -- arbitrary but deterministic, same "explicit stable
order over incidental order" precedent the VGSI sources use for their own
street/pid enumeration (never rely on incidental list/DB order).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class StormMatch:
    event_date: date
    event_type: str
    summary: str


def select_nearest_storm_event(
    year_built: int | None, storm_events: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Pick the single most recent `storm_events` row that qualifies for a
    parcel with the given `year_built`, or None if no qualifying event
    exists (including when `year_built` itself is unknown). See this
    module's docstring for the full reasoning.
    """
    if year_built is None:
        return None
    qualifying = [e for e in storm_events if e["event_date"].year >= year_built]
    if not qualifying:
        return None
    return max(qualifying, key=lambda e: (e["event_date"], int(e["event_id"])))


def format_storm_event_summary(event: dict[str, Any]) -> str:
    """Render a genuinely useful summary string -- event type, date, and
    magnitude when the event actually has one -- never just a raw ID.
    """
    magnitude = event.get("magnitude")
    magnitude_part = f" (magnitude {magnitude})" if magnitude else ""
    return f"{event['event_type']} on {event['event_date'].isoformat()}{magnitude_part}"


def compute_storm_match(year_built: int | None, storm_events: list[dict[str, Any]]) -> StormMatch | None:
    """Convenience wrapper: select + format in one call. Returns None
    under the exact same conditions `select_nearest_storm_event` does.
    """
    event = select_nearest_storm_event(year_built, storm_events)
    if event is None:
        return None
    return StormMatch(
        event_date=event["event_date"],
        event_type=event["event_type"],
        summary=format_storm_event_summary(event),
    )
