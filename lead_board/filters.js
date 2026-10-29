/*
 * Filter/toggle predicates for the interactive slider Lead Board.
 *
 * Plain CommonJS, no dependencies -- same "loadable by Node and inlined
 * into the page verbatim" discipline as `scoring.js`.
 *
 * **Siding-material / roof-cover-material filters, history** (2026-10-29
 * follow-up): the FIRST Step 0 pass measured coverage across every
 * scoreable parcel (state-only rows included) and found `exterior_wall_1`/
 * `roof_cover_material` at only ~25% overall / ~4% in claimed towns --
 * dropped as too sparse. A follow-up asked to re-measure against the
 * DEFAULT-filtered population instead (state-only rows excluded, the
 * view a viewer actually sees by default) -- there, coverage is 96.0%/
 * 95.8% overall and 73.5%/70.5% in claimed towns, comfortably over the
 * 40% bar. RESTORED. The original number wasn't wrong, it was measuring
 * the wrong population: state-only rows (the state-CAMA-merge majority)
 * never carry these fields at all, so including them in the denominator
 * made a well-populated SCRAPED signal look sparse.
 *
 * Both filters bucket a parcel with no material on file as `'Unknown'`
 * (`materialsOf`/`roofCoverOf` below) rather than excluding it from the
 * filter's own option list -- this makes the bucket visible and
 * selectable instead of silently dropping unknowns, and means a
 * state-only row (never has material data) shows as `'Unknown'` the
 * moment the "show state-data-only rows" toggle makes it visible at
 * all, with no separate state-only-specific logic needed here.
 */
'use strict';

const UNKNOWN_MATERIAL = 'Unknown';

/**
 * Reads the PRECOMPUTED `siding_families`/`roof_family` fields the
 * export/build scripts already wrote (Python, via `extscorer.normalize
 * .materials` -- see that module's own docstring) -- no classification
 * logic lives here, only the "missing data -> Unknown" bucketing
 * convention, so the filter and the real siding-score dispatch can never
 * silently classify the same raw text two different ways.
 */
function materialsOf(parcel) {
  return parcel.siding_families && parcel.siding_families.length > 0 ? parcel.siding_families : [UNKNOWN_MATERIAL];
}

function roofCoverOf(parcel) {
  return parcel.roof_family || UNKNOWN_MATERIAL;
}

function isClaimedTerritory(parcel, soldTowns) {
  const allowed = new Set(soldTowns.map((t) => t.toLowerCase()));
  return allowed.has((parcel.town || '').toLowerCase());
}

function isWorked(parcel) {
  // No pipeline row at all means unworked, same as a 'new' row -- only a
  // non-'new' status counts as worked. See Prompt W's follow-up addendum:
  // deliberately NOT the digest's own dedup rule (which excludes a lead
  // the moment ANY lead_pipeline row exists, 'new' included) -- the board
  // wants to distinguish "surfaced but not yet worked" from "worked".
  const status = parcel.flags.pipeline_status;
  return status !== null && status !== undefined && status !== 'new';
}

function isMailedOrShown(parcel) {
  return Boolean(parcel.flags.mailed_or_shown);
}

function isUnreachable(parcel) {
  return Boolean(parcel.flags.is_absentee) || Boolean(parcel.flags.is_delinquent);
}

function isStateOnly(parcel) {
  return Boolean(parcel.flags.is_state_only);
}

function hasRealPermitHistory(parcel) {
  return Boolean(parcel.flags.permit_data_available) && !parcel.flags.permit_history_short;
}

function inRange(value, min, max) {
  if (value === null || value === undefined) return true; // unknown passes through, never silently excluded
  if (min !== null && min !== undefined && value < min) return false;
  if (max !== null && max !== undefined && value > max) return false;
  return true;
}

/**
 * `filterState` shape:
 * {
 *   towns: Set<string> | null,           // null/empty = all towns
 *   yearBuiltMin, yearBuiltMax: number | null,
 *   canopyMin, canopyMax: number | null, // pct_tree_canopy_nearby
 *   jobSizePctMin, jobSizePctMax: number | null, // 0-100, against the jobSize component
 *   sidingMaterials: Set<string> | null, // against materialsOf(parcel); 'Unknown' is a selectable bucket
 *   roofCoverMaterials: Set<string> | null, // against roofCoverOf(parcel); 'Unknown' is a selectable bucket
 *   requireRealPermitHistory: boolean,
 *   hideClaimed: boolean,
 *   hideWorked: boolean,
 *   hideMailed: boolean,
 *   hideUnreachable: boolean,
 *   showStateOnly: boolean,              // when false, state-only rows are excluded entirely
 * }
 * `soldTowns`: array of claimed-town names (from export metadata).
 * `jobSizePercentiles`: Map<lead_key, 0-1 percentile> (same map `rankLeads`
 * was given) -- needed here since the job-size RANGE filter operates on
 * the computed percentile, not a raw field, same basis as the slider.
 */
function applyFilters(parcels, filterState, soldTowns, jobSizePercentiles) {
  return parcels.filter((parcel) => {
    if (filterState.towns && filterState.towns.size > 0 && !filterState.towns.has(parcel.town)) {
      return false;
    }
    if (!inRange(parcel.year_built, filterState.yearBuiltMin, filterState.yearBuiltMax)) {
      return false;
    }
    if (!inRange(parcel.pct_tree_canopy_nearby, filterState.canopyMin, filterState.canopyMax)) {
      return false;
    }
    if (filterState.jobSizePctMin !== null || filterState.jobSizePctMax !== null) {
      const pct = jobSizePercentiles ? jobSizePercentiles.get(parcel.lead_key) : null;
      const pct100 = pct === null || pct === undefined ? null : pct * 100;
      if (!inRange(pct100, filterState.jobSizePctMin, filterState.jobSizePctMax)) {
        return false;
      }
    }
    if (filterState.sidingMaterials && filterState.sidingMaterials.size > 0) {
      const materials = materialsOf(parcel);
      if (!materials.some((m) => filterState.sidingMaterials.has(m))) {
        return false;
      }
    }
    if (filterState.roofCoverMaterials && filterState.roofCoverMaterials.size > 0) {
      if (!filterState.roofCoverMaterials.has(roofCoverOf(parcel))) {
        return false;
      }
    }
    if (filterState.requireRealPermitHistory && !hasRealPermitHistory(parcel)) {
      return false;
    }
    if (filterState.hideClaimed && isClaimedTerritory(parcel, soldTowns)) {
      return false;
    }
    if (filterState.hideWorked && isWorked(parcel)) {
      return false;
    }
    if (filterState.hideMailed && isMailedOrShown(parcel)) {
      return false;
    }
    if (filterState.hideUnreachable && isUnreachable(parcel)) {
      return false;
    }
    if (!filterState.showStateOnly && isStateOnly(parcel)) {
      return false;
    }
    return true;
  });
}

const DEFAULT_FILTER_STATE = {
  towns: null,
  yearBuiltMin: null,
  yearBuiltMax: null,
  canopyMin: null,
  canopyMax: null,
  jobSizePctMin: null,
  jobSizePctMax: null,
  sidingMaterials: null,
  roofCoverMaterials: null,
  requireRealPermitHistory: false,
  hideClaimed: true,
  hideWorked: true,
  hideMailed: true,
  hideUnreachable: true,
  showStateOnly: false,
};

if (typeof module !== 'undefined') {
  module.exports = {
    isClaimedTerritory,
    isWorked,
    isMailedOrShown,
    isUnreachable,
    isStateOnly,
    hasRealPermitHistory,
    materialsOf,
    roofCoverOf,
    UNKNOWN_MATERIAL,
    inRange,
    applyFilters,
    DEFAULT_FILTER_STATE,
  };
}
