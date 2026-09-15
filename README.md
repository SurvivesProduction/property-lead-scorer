# property-lead-scorer

Public template: scores residential properties as exterior-renovation
(siding/roofing) lead candidates from three always-on signals --
property/roof age, tree-canopy coverage nearby, and storm/hail event
history -- plus two optional signals for a downstream deployment to
enable once its sources support them: a siding-material-age proxy
(material + year built, for sources with no real renovation history) and
real permit history (for sources that expose actual siding/roofing permit
records) -- instead of guessing which homes in a service area are due for
work.

This is the generic/free version -- no real target towns, no client-tuned
thresholds, no real data. See the full build for a real client
deployment: [property-lead-scorer-full](../property-lead-scorer-full).

## What this is

`extscorer` is a small, reusable framework for turning "property records
from N towns' assessor portals, plus two region-wide bulk datasets" into
one scored, ranked, debuggable lead list:

- `LeadDataSource` -- the abstract `fetch -> parse -> normalize` pipeline
  every concrete source implements. Unlike a scraper-only framework, this
  interface is deliberately shape-agnostic: a **scrape** source (one HTTP
  request per town, one output record) and a **bulk-dataset** source (one
  file load covering many rows, many output records) both satisfy it
  without either being forced into the other's mold -- see
  `sources/base.py`'s docstring.
- `extscorer.sources.registry` -- a `@register_source("source_slug")`
  decorator and `get_source_class(slug)` lookup, so adding a new town or
  dataset is "write one new source module," not "touch shared code."
- `ParcelLeadRecord` / `StormEventRecord` -- the two normalized schemas
  (not one -- a parcel isn't a kind of storm event) every source produces.
- `extscorer.scoring.basic` -- pure, client-agnostic scoring functions:
  property-age (leading signal), tree-canopy (a non-linear "bathtub"
  curve -- both heavy cover and a fully exposed site raise risk), and
  storm-recency (lighter supporting signal) are always evaluated;
  siding-material-age (a proxy, opt-in) and real permit-history (opt-in,
  and self-suppresses the siding-age proxy per parcel when both are
  available -- see that module's own docstring) are two further optional
  signals a downstream deployment can turn on per its own data sources.
  All combine into one `lead_score` as a weighted average of whichever
  signals are actually active for a given parcel, each component
  preserved for debugging, plus a deterministic ranking tiebreak.
- A Postgres client (`extscorer.db.client`) that upserts parcels (keyed
  per client+town+parcel id) and storm events (global reference data,
  keyed on NOAA's own event id).

It intentionally does not include any real scraping targets, client
identifiers, or hosting-provider-specific wiring (e.g. Supabase). Those
live in a paid/full deployment layer that installs this package as a
dependency and adds the client-specific pieces on top.

## Why no real source yet

No real VGSI town card, NOAA storm CSV, or tree-canopy raster fetcher has
been built yet -- per the same data-source-refinement workflow used for
the other tools in this family, a source doesn't get built against a real
target until it's been manually inspected and confirmed to actually work
the way it's assumed to. `scripts/run_demo.py` demonstrates the full
framework -- including the registry mechanism and both source shapes --
against small hardcoded synthetic sources instead.

## Install

Requires Python >=3.11 and a Postgres database (only needed once you're
ready to run migrations for real -- the demo script below needs neither).

```bash
pip install -e .
# or, with test dependencies:
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in your own values:

```bash
cp .env.example .env
```

`DATABASE_URL` is the preferred way to configure the connection; if it's
unset, the standard `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`
variables are used instead.

## Run migrations

```bash
python scripts/migrate.py
```

This applies every SQL file under `src/extscorer/migrations/`
(`001_init_schema.sql`, which creates `parcels` and `storm_events`) in
order. Every migration is written with `if not exists` guards, so it's
safe to rerun.

## Run the demo

```bash
python scripts/run_demo.py --client-id demo
```

No database needed -- runs two hardcoded example sources (one
scrape-shaped, one bulk-dataset-shaped) through the exact same
`LeadDataSource.run()` pipeline and prints what each produces. Not real
data -- a reference for what a real source's `fetch`/`parse`/`normalize`
methods and its `@register_source(...)` registration should look like.

## How the pieces fit together

- **`extscorer.sources.base.LeadDataSource`** -- subclass once per town or
  dataset. `fetch()` retrieves raw content, `parse()` turns it into a
  list of raw record dicts, `normalize()` turns one raw record into a
  normalized model (`ParcelLeadRecord` or `StormEventRecord`, depending
  on the source). `run()` orchestrates all three.
- **`extscorer.sources.registry`** -- `register_source(slug)` (class
  decorator) and `get_source_class(slug)` (lookup). Raises on a
  conflicting duplicate slug registration rather than silently
  overwriting.
- **`extscorer.normalize.schema`** -- `ParcelLeadRecord` (the per-property
  lead shape) and `StormEventRecord` (global storm-history reference
  data). See each model's own docstring for field-by-field reasoning.
- **`extscorer.scoring.basic`** -- `score_property`/`rank_candidates` and
  the three component-score functions. All default weights/thresholds are
  explicitly documented as proposed, not final -- see the module
  docstring.
- **`extscorer.db.client`** -- `upsert_parcel` (keyed on `client_id,
  town, parcel_id`), `upsert_storm_event` (keyed on `source, event_id`,
  no client scoping). `upsert_parcel` preserves enrichment-only fields
  (geocoding/canopy/storm/score/permit data) on a re-scrape that doesn't
  provide them, rather than overwriting with `None` -- see its own
  docstring for why this matters for any source whose own scrape never
  populates those columns.

A downstream deployment (like the full/paid repo) adds concrete source
subclasses for real towns/datasets, seeds real client config, and digest
integration on top -- without needing to touch or fork this package's
code.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Covers `ParcelLeadRecord`/`StormEventRecord` schema validation, the
source registry's register/resolve/conflict behavior,
`LeadDataSource.run()`'s orchestration for both a scrape-shaped and a
bulk-dataset-shaped source, and every scoring function (including a
deliberate synthetic tie to test `rank_candidates`'s deterministic
tiebreak -- see Tool 2's real 214-way tie for why this matters).
