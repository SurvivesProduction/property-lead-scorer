from typing import Any

from extscorer.normalize.schema import ParcelLeadRecord, StormEventRecord
from extscorer.sources.base import LeadDataSource


class _ScrapeShapedSource(LeadDataSource):
    """One fetch() call, HTML-shaped raw content, one output record --
    the shape a real per-town VGSI fetcher will follow."""

    def fetch(self) -> dict[str, Any]:
        return {"town": "Canterbury", "county": "Windham", "address": "1 Fake St", "parcel_id": "1"}

    def parse(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        return [raw]

    def normalize(self, raw_record: dict[str, Any]) -> ParcelLeadRecord:
        return ParcelLeadRecord(client_id=self.client_id, raw_data=raw_record, **raw_record)


class _BulkDatasetShapedSource(LeadDataSource):
    """One fetch() call, CSV-shaped raw content, many output records --
    the shape a real NOAA storm-events fetcher will follow."""

    def fetch(self) -> list[dict[str, Any]]:
        return [
            {
                "event_id": "1",
                "county": "Windham",
                "state": "CT",
                "event_date": "2023-07-14",
                "event_type": "Hail",
            },
            {
                "event_id": "2",
                "county": "Windham",
                "state": "CT",
                "event_date": "2020-08-04",
                "event_type": "Thunderstorm Wind",
            },
        ]

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def normalize(self, raw_record: dict[str, Any]) -> StormEventRecord:
        return StormEventRecord(raw_data=raw_record, **raw_record)


def test_run_orchestrates_a_scrape_shaped_source_one_record_per_fetch() -> None:
    source = _ScrapeShapedSource(client_id="demo", source_slug="scrape-source")
    records = list(source.run())

    assert len(records) == 1
    assert isinstance(records[0], ParcelLeadRecord)
    assert records[0].parcel_id == "1"
    assert records[0].client_id == "demo"


def test_run_orchestrates_a_bulk_dataset_shaped_source_many_records_per_fetch() -> None:
    source = _BulkDatasetShapedSource(client_id="demo", source_slug="bulk-source")
    records = list(source.run())

    assert len(records) == 2
    assert all(isinstance(r, StormEventRecord) for r in records)
    assert [r.event_id for r in records] == ["1", "2"]
