/*
 * Client-side re-ranking for the interactive slider Lead Board (Prompt W).
 *
 * v1 re-weights PRECOMPUTED components only -- this file never recomputes
 * `property_age_score`/`canopy_score`/`storm_score`/`siding_score` from
 * raw fields, it just re-runs the weighted-average combine step
 * `extscorer.scoring.basic.score_property` itself does, against each
 * parcel's own already-persisted `score_*_component` columns (see
 * `property-lead-scorer-full/scripts/export_lead_board_data.py`'s
 * `components` field). Two new OPTIONAL components (`jobSize`/
 * `saleRecency`) are computed here, client-side, from percentile rank --
 * see `computeJobSizeComponent`/`computeSaleRecencyComponent` below --
 * since no such persisted column exists in the DB to reuse.
 *
 * Plain CommonJS (`module.exports`), no build step, no dependencies --
 * loadable both by Node (`require`, the parity/unit tests) and by the
 * board page itself (inlined verbatim into a <script> tag by the build
 * scripts in both repos -- `module.exports` is simply never reached
 * there since no `module` global exists in a browser `<script>`, which
 * is fine, nothing in the page needs it).
 */
'use strict';

/**
 * The combine step `score_property` itself uses: weighted AVERAGE of every
 * component that is present (not null/undefined), dividing by the SUM of
 * those components' own weights -- not a plain weighted sum. Mirrors
 * `score_property`'s exact arithmetic and operation order (one running
 * `weightedSum`/`totalWeight` pair, components folded in a fixed order)
 * so floating-point results match the stored `lead_score` bit-for-bit
 * (not merely "close"), not just within the 1e-9 parity tolerance.
 *
 * `components`/`weights` are plain objects keyed by the same component
 * names: `property`, `canopy`, `storm`, `siding`, `jobSize`, `saleRecency`.
 * A component absent from `components` (or `null`/`undefined`) is skipped
 * entirely, same as `score_property`'s `siding_component is None` check --
 * its weight does NOT enter `totalWeight` either, so disabling a signal
 * (e.g. the storm slider, which `score_property` never actually had this
 * option for, but the board does) behaves identically to Python's
 * `enable_siding_signal=False` path for siding specifically, generalized
 * here to every component.
 *
 * Fixed combine order matches `score_property`'s own: property, canopy,
 * storm, then siding, jobSize, saleRecency -- floating-point addition is
 * not associative, so this order must stay fixed for bit-for-bit parity.
 */
const COMPONENT_ORDER = ['property', 'canopy', 'storm', 'siding', 'jobSize', 'saleRecency'];

function computeScore(components, weights) {
  let weightedSum = 0;
  let totalWeight = 0;
  for (const key of COMPONENT_ORDER) {
    const value = components[key];
    if (value === null || value === undefined) continue;
    const weight = weights[key] || 0;
    weightedSum += weight * value;
    totalWeight += weight;
  }
  return totalWeight > 0 ? weightedSum / totalWeight : 0;
}

/**
 * Percentile rank (0-1, higher = more extreme/larger) of `value` within
 * `sortedValues` (ascending, pre-sorted by the caller once per render --
 * O(n log n) sort amortized across every lead, not per-lead). Returns
 * `null` for a `value` of `null`/`undefined` -- the caller (`withJobSize
 * Component`/`withSaleRecencyComponent`) maps that to the neutral 0.5
 * "unknown" convention every other signal in this project already uses
 * (`canopy_score`/`siding_age_score`'s own missing-data handling),
 * rather than fabricating a rank for data that was never on file.
 *
 * Rank is the fraction of values <= `value` (inclusive, via a binary
 * search for the last occurrence) -- ties share the SAME rank (the
 * highest rank among the tied group), not split arbitrarily.
 */
function percentileRank(sortedValues, value) {
  if (value === null || value === undefined) return null;
  if (sortedValues.length === 0) return null;
  if (sortedValues.length === 1) return 1.0;

  let lo = 0;
  let hi = sortedValues.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sortedValues[mid] <= value) lo = mid + 1;
    else hi = mid;
  }
  // lo is now the count of values <= value.
  return lo / sortedValues.length;
}

/**
 * Job-size proxy: percentile rank of `living_area_sqft`, falling back to
 * `assessed_value` when sqft is unknown but assessed value is on file
 * (both are real-world "how big a job" proxies -- sqft is more direct,
 * assessed value the next-best signal when it's missing). Returns 0.5
 * (neutral, never fabricated) when NEITHER is known for a parcel, same
 * "unknown is neutral" convention `canopy_score`/`siding_age_score`
 * already use -- see module docstring.
 */
function computeJobSizeComponent(parcel, sortedSqft, sortedAssessedValue) {
  if (parcel.living_area_sqft !== null && parcel.living_area_sqft !== undefined) {
    const rank = percentileRank(sortedSqft, parcel.living_area_sqft);
    if (rank !== null) return rank;
  }
  if (parcel.assessed_value !== null && parcel.assessed_value !== undefined) {
    const rank = percentileRank(sortedAssessedValue, parcel.assessed_value);
    if (rank !== null) return rank;
  }
  return 0.5;
}

/**
 * Sale-recency component: percentile rank of `last_sale_year` -- higher
 * rank means a MORE RECENT sale, which this signal treats as LOWER
 * priority (a recently-sold property is less likely to need exterior
 * work pitched right now, and/or the new owner may still be settling
 * in) -- so the returned score is `1 - rank`, i.e. the LEAST recently
 * sold (or never-recorded) properties score highest. Returns 0.5
 * (neutral) when `last_sale_year` is unknown, same convention as
 * `computeJobSizeComponent`.
 */
function computeSaleRecencyComponent(parcel, sortedSaleYears) {
  if (parcel.last_sale_year === null || parcel.last_sale_year === undefined) return 0.5;
  const rank = percentileRank(sortedSaleYears, parcel.last_sale_year);
  if (rank === null) return 0.5;
  return 1 - rank;
}

/**
 * Deterministic tiebreak comparator matching `extscorer.scoring.basic
 * .rank_candidates`'s `sorted(..., reverse=True)` key EXACTLY, including
 * the reversed `parcel_id` order: `(score, living_area_sqft or 0,
 * -(year_built or 0), parcel_id)`, every field descending. Returns a
 * negative number when `a` sorts before `b` (standard `Array.prototype
 * .sort` comparator convention), matching `reverse=True` on every field
 * -- NOT merely "sort ascending then reverse the array" (that would
 * invert the stable-sort tie order Python's own `sorted(reverse=True)`
 * preserves for genuinely-equal keys).
 */
function compareLeadsDesc(a, b) {
  if (a.score !== b.score) return b.score - a.score;

  const aSqft = a.living_area_sqft || 0;
  const bSqft = b.living_area_sqft || 0;
  if (aSqft !== bSqft) return bSqft - aSqft;

  const aYear = a.year_built || 0;
  const bYear = b.year_built || 0;
  if (aYear !== bYear) return aYear - bYear; // oldest (smallest year_built) first

  if (a.parcel_id === b.parcel_id) return 0;
  return a.parcel_id < b.parcel_id ? 1 : -1; // descending (reverse=True) lexicographic
}

/**
 * Score and rank every parcel at the given weights, returning a new array
 * of `{...parcel, score, rank}` sorted by `compareLeadsDesc` -- `rank` is
 * 1-based position in this ranking. Does NOT filter -- callers apply
 * filters/toggles separately (see `filters.js`) before or after ranking
 * as appropriate; this function's only job is score + deterministic
 * order, mirroring `rank_candidates`'s own single responsibility.
 *
 * `jobSizeComponents`/`saleRecencyComponents` are `Map`s keyed by
 * `lead_key`, precomputed ONCE per full parcel set by the caller (via
 * `computeJobSizeComponent`/`computeSaleRecencyComponent` against the
 * FULL sorted-value arrays) -- percentile rank is only meaningful
 * relative to the whole population, so it must never be recomputed
 * against an already-filtered subset.
 */
function rankLeads(parcels, weights, jobSizeComponents, saleRecencyComponents) {
  const scored = parcels.map((parcel) => {
    const components = {
      property: parcel.components.property,
      canopy: parcel.components.canopy,
      storm: parcel.components.storm,
      siding: parcel.components.siding,
      jobSize: jobSizeComponents ? jobSizeComponents.get(parcel.lead_key) : undefined,
      saleRecency: saleRecencyComponents ? saleRecencyComponents.get(parcel.lead_key) : undefined,
    };
    const score = computeScore(components, weights);
    return Object.assign({}, parcel, { score, _components: components });
  });
  scored.sort(compareLeadsDesc);
  scored.forEach((lead, index) => {
    lead.rank = index + 1;
  });
  return scored;
}

// `module` doesn't exist in a browser <script> tag -- guarded so this
// file can be `require()`d by Node tests AND inlined verbatim into the
// page by the build scripts, with the same functions landing as plain
// globals either way (see this file's own module docstring).
if (typeof module !== 'undefined') {
  module.exports = {
    COMPONENT_ORDER,
    computeScore,
    percentileRank,
    computeJobSizeComponent,
    computeSaleRecencyComponent,
    compareLeadsDesc,
    rankLeads,
  };
}
