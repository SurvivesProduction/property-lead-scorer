"""Abstract base class every lead-data source implements -- whether it's a
per-parcel web scrape (VGSI, town by town) or a bulk-dataset load
(NOAA's storm-events CSVs). One shared interface, deliberately generic
about what a "raw record" is, precisely so both source *shapes* satisfy
it without either being force-fit into the other's mold:

- **Scrape-shaped** (e.g. a future VGSI-per-town fetcher): `fetch()`
  makes an HTTP request per target and returns HTML; `parse()` extracts
  the handful of fields off that one page; `normalize()` builds one
  `ParcelLeadRecord`. One `fetch()` call, typically one output record.

- **Bulk-dataset-shaped** (e.g. a future NOAA storm-events fetcher):
  `fetch()` downloads/reads one CSV file covering many events at once;
  `parse()` turns every row into a raw dict; `normalize()` builds one
  `StormEventRecord` per row. One `fetch()` call, many output records.

Both shapes reduce to the identical fetch -> parse -> normalize -> yield
pipeline below -- `run()` doesn't care which shape a concrete subclass
is, only that it can produce a raw payload, split it into raw record
dicts, and turn each dict into a normalized model.

**Tree canopy is deliberately NOT assumed to fit this interface.** What
that source actually needs to answer is "given a parcel's lat/lon,
what's the % tree canopy in a buffer around it?" -- a per-parcel *query*
against a raster, not a stream of discrete records to enumerate the way
a CSV's rows or a scraped page's fields are. A canopy fetcher could
still implement `LeadDataSource` for a coarse bulk load (e.g. yielding
grid-cell records), but the real zonal-stats-buffer join is a separate,
unsolved design question left for when that fetcher actually gets built
-- see this repo's README.

Concrete subclasses live in a downstream package (e.g. the paid
per-client deployment) and are parametrized per portal / dataset. This
class has no knowledge of any specific source.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class LeadDataSource(ABC):
    """Fetch -> parse -> normalize -> yield pipeline for one lead-data source.

    `source_slug` is the key a downstream deployment's `sources/registry.py`
    resolves a `clients/<client_id>/config.yaml` `targets:` entry to a
    concrete class through -- see `extscorer.sources.registry`.

    Unlike `oppscanner.scrapers.base.BaseOpportunityFetcher`, `normalize()`
    here is typed `-> Any` rather than one fixed model: this tool has two
    genuinely different normalized shapes (`ParcelLeadRecord` for a scrape
    source, `StormEventRecord` for a bulk-dataset source), not
    Tool 3's single `OpportunityRecord` shape. A concrete subclass's own
    `normalize()` return-type annotation is the real contract for that
    subclass.
    """

    def __init__(self, client_id: str, source_slug: str) -> None:
        self.client_id = client_id
        self.source_slug = source_slug

    @abstractmethod
    def fetch(self) -> Any:
        """Retrieve the raw content for this source (HTML, CSV text, JSON, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw: Any) -> list[dict[str, Any]]:
        """Parse raw fetched content into a list of raw record dicts.

        A scrape source typically returns a single-item list (one page,
        one record); a bulk-dataset source typically returns one item per
        row/feature in the loaded file.
        """
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_record: dict[str, Any]) -> Any:
        """Convert a single raw record dict into this source's normalized model."""
        raise NotImplementedError

    def run(self) -> Iterator[Any]:
        """Orchestrate fetch -> parse -> normalize -> yield normalized records."""
        raw = self.fetch()
        for raw_record in self.parse(raw):
            yield self.normalize(raw_record)
