#!/usr/bin/env python
"""Example end-to-end run of the extscorer framework.

This is a template/demo, NOT a real source. It deliberately shows BOTH
source shapes this tool has to support, registered via the exact
mechanism a real downstream deployment (e.g. `extscorer_full.sources`)
uses to add a new town or dataset -- write one source module, decorate
its class with `@register_source(...)`, and this orchestration code
never needs to import that module by name:

- `ExampleTownVgsiSource` -- **scrape-shaped**. `fetch()` stands in for
  one HTTP GET against one town's VGSI parcel card (one target, one
  page); `parse()` returns a single-item list; `normalize()` builds one
  `ParcelLeadRecord`.
- `ExampleCountyStormEventSource` -- **bulk-dataset-shaped**. `fetch()`
  stands in for downloading/reading one NOAA storm-events CSV covering a
  whole county's history at once; `parse()` splits it into many raw row
  dicts; `normalize()` builds one `StormEventRecord` per row.

No live database is used here -- this repo's schema hasn't been run
against any real database yet (see README). This script only proves the
`LeadDataSource.run()` pipeline genuinely supports both shapes end to
end, in memory.

Usage:
    python scripts/run_demo.py --client-id demo
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from extscorer.normalize.schema import ParcelLeadRecord, StormEventRecord
from extscorer.sources.base import LeadDataSource
from extscorer.sources.registry import get_source_class, register_source

_EXAMPLE_TOWN_SLUG = "example-town-vgsi"
_EXAMPLE_STORM_SLUG = "example-county-storm-events"

# Stands in for one town's single VGSI parcel-card page -- a scrape
# source's fetch() typically hits one URL per target and gets back one
# record's worth of fields.
_EXAMPLE_VGSI_CARD: dict[str, Any] = {
    "town": "Canterbury",
    "county": "Windham",
    "address": "123 Example Rd",
    "parcel_id": "0042",
    "source_url": "https://gis.vgsi.com/canterburyct/Parcel.aspx?pid=42",
    "year_built": 1978,
    "living_area_sqft": 1850,
    "roof_cover_material": "Asphalt Shingle",
}

# Stands in for one NOAA storm-events CSV file covering Windham County --
# a bulk-dataset source's fetch() typically loads one file covering many
# rows at once.
_EXAMPLE_STORM_CSV_ROWS: list[dict[str, Any]] = [
    {
        "event_id": "10001",
        "county": "Windham",
        "state": "CT",
        "event_date": "2023-07-14",
        "event_type": "Hail",
        "magnitude": "1.00 in",
        "narrative": "Quarter-size hail reported near Putnam.",
        "property_damage_estimate": "5000",
    },
    {
        "event_id": "10002",
        "county": "Windham",
        "state": "CT",
        "event_date": "2020-08-04",
        "event_type": "Thunderstorm Wind",
        "magnitude": "60 kts",
        "narrative": "Trees and wires down across Brooklyn and Pomfret.",
        "property_damage_estimate": "25000",
    },
]


@register_source(_EXAMPLE_TOWN_SLUG)
class ExampleTownVgsiSource(LeadDataSource):
    """Template scrape-shaped source: one town, one parcel card."""

    def fetch(self) -> dict[str, Any]:
        return _EXAMPLE_VGSI_CARD

    def parse(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        return [raw]

    def normalize(self, raw_record: dict[str, Any]) -> ParcelLeadRecord:
        return ParcelLeadRecord(
            client_id=self.client_id,
            raw_data=raw_record,
            **raw_record,
        )


@register_source(_EXAMPLE_STORM_SLUG)
class ExampleCountyStormEventSource(LeadDataSource):
    """Template bulk-dataset-shaped source: one CSV, many events."""

    def fetch(self) -> list[dict[str, Any]]:
        return _EXAMPLE_STORM_CSV_ROWS

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def normalize(self, raw_record: dict[str, Any]) -> StormEventRecord:
        return StormEventRecord(raw_data=raw_record, **raw_record)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the example extscorer demo.")
    parser.add_argument("--client-id", default="demo", help="Client id to tag parcel records with.")
    args = parser.parse_args()

    print("-- Scrape-shaped source --")
    town_source_cls = get_source_class(_EXAMPLE_TOWN_SLUG)
    town_source = town_source_cls(client_id=args.client_id, source_slug=_EXAMPLE_TOWN_SLUG)
    parcel_count = 0
    for record in town_source.run():
        parcel_count += 1
        print(f"  ParcelLeadRecord: {record.town} parcel {record.parcel_id} -- {record.address} (built {record.year_built})")
    print(f"  {parcel_count} record(s) from 1 fetch() call.\n")

    print("-- Bulk-dataset-shaped source --")
    storm_source_cls = get_source_class(_EXAMPLE_STORM_SLUG)
    storm_source = storm_source_cls(client_id=args.client_id, source_slug=_EXAMPLE_STORM_SLUG)
    storm_count = 0
    for record in storm_source.run():
        storm_count += 1
        print(f"  StormEventRecord: {record.event_type} in {record.county}, {record.state} on {record.event_date} (id={record.event_id})")
    print(f"  {storm_count} record(s) from 1 fetch() call.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
