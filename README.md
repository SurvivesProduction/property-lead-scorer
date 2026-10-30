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

## Why no real source here

No real VGSI town card, NOAA storm CSV, or tree-canopy raster fetcher
lives in THIS package, by permanent design -- same as every other tool in
this family, real scraping targets and client-specific wiring live in the
paid `-full` deployment layer
([property-lead-scorer-full](../property-lead-scorer-full)), never here.
This isn't a "not built yet" gap: real VGSI/propertyrecordcards.com/
CT-statewide-CAMA/NOAA/canopy sources for 9 real towns (added Windham,
2026-10-26, via the state Parcel+CAMA dataset -- AxisGIS is Windham's own
GIS system and stays off-limits to automation, see that repo's own
ARCHITECTURE.md section 21) exist and are live-confirmed in that other
repo -- they were never going to land in this one. `scripts/run_demo.py` demonstrates the full framework --
including the registry mechanism and both source shapes -- against small
hardcoded synthetic sources instead, and stays that way permanently, not
as a placeholder for a future real fetcher.

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
(`001_init_schema.sql`, which creates `parcels` and `storm_events`, through
`008_add_lead_pipeline.sql`, which adds the shared-Sheet working pipeline
table -- see below) in order. Every migration is written with `if not
exists` guards, so it's safe to rerun.

## Run the demo

```bash
python scripts/run_demo.py --client-id demo
```

No database needed -- runs two hardcoded example sources (one
scrape-shaped, one bulk-dataset-shaped) through the exact same
`LeadDataSource.run()` pipeline and prints what each produces. Not real
data -- a reference for what a real source's `fetch`/`parse`/`normalize`
methods and its `@register_source(...)` registration should look like.

## Lead Board (interactive slider sales tool)

`lead_board/` holds a self-contained, offline HTML page -- weight sliders
and filters re-rank a client's scored leads LIVE in the browser, no
backend, no login. Built for screen-sharing with a crew: which knobs they
reach for is itself a signal for what to refine next.

- **`lead_board/scoring.js`** -- re-weights each parcel's already-
  persisted `score_*_component` columns (never recomputes the underlying
  curves) plus two new OPTIONAL components computed client-side from
  percentile rank -- job size (`living_area_sqft`, falling back to
  `assessed_value`) and sale recency (`last_sale_year`) -- both default
  weight 0, so the default ranking is byte-for-byte unchanged until a
  viewer actually moves one.
  - **Parity guarantee**: at the default weights and the stored as-of
    year, this module's score matches the real, persisted `lead_score`
    for every scoreable parcel within 1e-9, and its default ranking
    exactly matches the database's own ordering, tiebreak included
    (`living_area_sqft` desc, then `year_built` asc/oldest-first, then
    `parcel_id` DESCENDING -- `rank_candidates`'s own `sorted(...,
    reverse=True)` applies to every tuple field, parcel_id included).
    Verified against the real population in
    `property-lead-scorer-full/tests_js/test_parity.js` (that repo has
    the real data; this one only has synthetic fixtures).
- **`lead_board/filters.js`** -- town/year/canopy/job-size range filters,
  siding-material and roof-cover multi-selects, "has real permit history"
  (`permit_data_available AND NOT permit_history_short`), and five
  toggles (hide claimed territory, hide worked, hide mailed/shown, hide
  unreachable, show state-data-only -- defaults ON/ON/ON/ON/OFF).
  - **Siding/roof filters, history**: a first Step 0 pass measured
    coverage across ALL scoreable parcels (state-only included) and found
    the raw text fields at only ~25% overall / ~4% in claimed towns --
    dropped as too sparse. A follow-up re-measured against the DEFAULT-
    filtered population (state-only rows excluded, what a viewer actually
    sees by default) and found 96%/96% overall, 73%/70% in claimed towns
    -- comfortably over the bar. RESTORED, but not as raw text: the real
    data has ~85/~26 distinct free-text variants from inconsistent
    scraping ("Clapboard" vs "Clapboards" vs "Clapboards/Board & Batten"),
    an unusable wall of near-duplicate chips. `extscorer.normalize
    .materials` (public repo's Python package) classifies each raw value
    into a small family set instead -- reusing `extscorer.scoring.basic`'s
    own siding-family keyword list for siding ("one shared mapping, not a
    second copy in JS"; a composite value like "Vinyl Siding/Clapboards"
    matches BOTH the Vinyl and Durable chips, unlike the single-family
    dispatch scoring itself uses) and a new roof-only classifier (no
    scoring equivalent exists for `roof_cover_material`) -- see that
    module's own docstring. The board's JS just reads the precomputed
    `siding_families`/`roof_family` fields; no classification logic lives
    client-side. Each chip shows a live count (every OTHER active
    filter/toggle applied, that dimension's own selection cleared) and
    hides itself at zero. The `siding` WEIGHT slider was never affected
    by any of this -- its `score_siding_component` is 100% present
    (neutral 0.5 when the raw material is unknown) regardless of the raw
    text's own sparsity.
- **`lead_board/presets.js`** -- "Darren default" (the real config
  weights), "Siding-focused" (siding is the heaviest weight, 0.70),
  "Bigger jobs" (job size becomes meaningful while property age still
  matters) -- see the file's own docstring for the exact numbers and why.
  - **Siding-focused, 2026-10-30 fix**: the original version (property=
    0.30, siding=0.50) measured 19-20/20 overlap with Darren default's
    top 20 against the real population -- not a tuning miss, a
    structural fact: `_durable_material_age_score` saturates to the SAME
    1.0 ceiling `property_age_score` approaches for the same old house,
    so any `property_weight > 0` keeps re-pinning the identical ancient-
    durable-sided properties no matter how heavily siding is weighted
    alongside it (confirmed directly: even `property_weight=0`/
    `siding_weight=1.0` alone still returns a 100%-durable-material top
    20, zero vinyl houses -- vinyl's own curve caps at 0.60, strictly
    below durable's 1.0, so no linear reweighting of the real scoring
    formula can ever surface a vinyl-sided house over a durable-sided
    one). A literal "Vinyl-era" preset is therefore not buildable without
    a material filter. Fixed by dropping `property_weight` to 0 and
    adding canopy (0.15) + job size (0.10) as real differentiators:
    measured 7/20 overlap with Darren default now (target was <=14/20),
    11/20 with Bigger Jobs (a genuinely different cut, not a near-copy).
    Regression-guarded against the real population in
    `property-lead-scorer-full/tests_js/test_preset_overlap.js`.
- **`lead_board/state.js`** -- every slider/filter/toggle value round-
  trips through the URL hash (base64url-encoded JSON); "Copy settings"
  copies the same JSON to the clipboard.
- **`lead_board/template.html`** + **`lead_board/app.js`** -- the page
  skeleton (light/dark via `prefers-color-scheme` + a manual toggle,
  mobile-responsive) and its DOM wiring.
  - **Layout, 2026-10-30**: the results list is the FIRST panel (with the
    live count and a one-line always-visible filter summary above it);
    Weights and Towns/Filters are collapsible `<details>` panels, open by
    default on desktop and closed on phone (set once from the viewport
    width at load, never fought by a viewer's own manual toggle).
  - **Rank numbering, 2026-10-30 fix**: a row's `#N` and its rank-change
    arrow are now both LOCAL to the current filter set -- `renderResults`
    filters first, then ranks that same filtered subset twice (current
    weights for the shown order, Darren default for the arrow's
    baseline), so `#7` really means "7th among what's visible" and the
    arrow means "moved within this same visible set." The old version
    ranked the full 24,578-parcel population once, unfiltered, then
    sliced -- `#4172` on a narrowed view, and an arrow comparing against
    a baseline that included rows the viewer couldn't even see.
  - **Theme toggle, 2026-10-30 fix**: the first click now always visibly
    switches. The old handler checked only whether `data-theme` had been
    explicitly set, not the EFFECTIVE current scheme -- a system-dark
    visitor's first click set `data-theme="dark"` explicitly, the SAME
    appearance already showing, a no-op that only became visible on the
    second press. Fixed to read `prefers-color-scheme` as the fallback
    when no explicit attribute is set yet.
  - No raw field names or raw scores in the main results list --
    component bars and the two per-lead links only appear once a row is
    expanded: **"View record card"** (the real `source_url`, when
    present -- "No record link" otherwise, never a dead button) and
    **"See it on the map"** (a Google Maps search link built from
    address + town + "CT", `property-lead-scorer-full/scripts
    /export_lead_board_data.py`'s `map_url` field -- omitted entirely, not
  shown broken, for the handful of rows with no house-numbered address).
  The two are independent -- a row can have either, both, or neither.

`scripts/build_demo_board.py` inlines the template + JS modules + a fully
synthetic fixture (fake towns/streets, covering a claimed town, a
Windham-shaped short-permit-history town, worked/unworked/mailed rows,
state-only rows, and sparse sale dates) into `demo/lead_board_demo.html`
-- safe to commit, safe to screen-share. The REAL-data build
(`property-lead-scorer-full/scripts/build_lead_board.py`) lives in the
full repo, writes to its own gitignored `output/`, and is never committed
-- see that repo's own README/ARCHITECTURE.

Node tests (no framework installed -- `tests_js/_runner.js` is a ~30-line
dependency-free runner; this project's Node predates the built-in test
runner added in Node 18):

```bash
node tests_js/run_all.js
```

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
- **`extscorer.normalize.address`** -- shared owner-mailing-address-vs-
  property-address comparison (`is_owner_address_mismatch` and its
  helpers). A mismatch is a real absentee-owner signal, not proof of
  vacancy on its own -- see the module's own docstring for why it's a
  deprioritization signal at the digest layer rather than a harder claim
  baked into the schema. Also reused (2026-09-16) to match a permit-
  history source's own address column against an already-scraped parcel's
  address (`normalize_street_address`), not just for the absentee check.
- **`extscorer.normalize.permits`** -- shared exterior-relevant-permit
  classification (`is_exterior_permit`). A downstream deployment's real
  permit-history sources both need the identical judgment call ("does this
  permit's own type/description describe exterior work"), so the keyword
  list lives in one place rather than drifting apart across sources.
- **`extscorer.digest.copy`/`extscorer.digest.selection`** -- the
  client-facing digest layer. `copy.py` renders a parcel's real signal
  values (never raw scores) into plain language for a non-technical
  reader, and must be updated in the same prompt as any change to
  `scoring.basic`'s active signals or weights (see its own module
  docstring's standing rule). `selection.py` picks which ranked leads
  actually go out: `is_likely_unreachable_owner` excludes a parcel whose
  owner's mailing address doesn't match the property address, or whose
  town shows an outstanding tax balance -- either is a real signal the
  property may be vacant or not a live sales conversation. This exclusion
  is digest-only by design: `rank_candidates`'s own output and the
  internal ops dashboard intentionally keep showing every scoreable
  parcel, unfiltered, for debugging.
- **`extscorer.lead_pipeline.lead_key`** / **`select_new_leads_for_pipeline`**
  (added for the shared Google Sheet working pipeline, see the full repo's
  `extscorer_full.sheets` package) -- `lead_key(town, parcel_id)` is the
  stable `"{town}:{parcel_id}"` string identifying a lead across the
  digest, the `lead_pipeline` table (`migrations/008_add_lead_pipeline.sql`),
  and the Sheet's own Master tab; safe because `parcels`' own
  `unique (client_id, town, parcel_id)` constraint already guarantees
  `(town, parcel_id)` is unique per client. `select_new_leads_for_pipeline`
  is `select_unsent_leads`'s sibling: same ranked-pairs shape and owner-
  exclusion, but its dedup check is "already in `lead_pipeline`" (any
  status) rather than "already in `lead_digest_sends`" -- a worked lead
  stays visible on the Sheet forever and is never re-surfaced as new.
  `lead_digest_sends` is unchanged in shape and still written after a real
  push, but now means only "was pushed to the Sheet," not "was the digest's
  dedup source."

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
