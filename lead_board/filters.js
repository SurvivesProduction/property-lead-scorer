/*
 * Filter/toggle predicates for the interactive slider Lead Board.
 *
 * Plain CommonJS, no dependencies -- same "loadable by Node and inlined
 * into the page verbatim" discipline as `scoring.js`.
 *
 * Two filters Prompt W originally asked for -- "siding material
 * multi-select" and "roof cover multi-select" -- are DELIBERATELY NOT
 * implemented here: Step 0's real coverage report found `exterior_wall_1`/
 * `roof_cover_material` populated on only ~25% of all scoreable parcels,
 * and WORSE (4.1-4.4%) within the three claimed towns specifically --
 * the raw material/roof TEXT fields are a scrape-only signal, essentially
 * absent on the thousands of state-CAMA-merge rows. The `siding_weight`
 * SLIDER stays (its underlying `score_siding_component` is 100% present,
 * defaulting to a neutral 0.5 when the raw material is unknown, the same
 * "unknown is neutral" convention the scoring module already documents)
 * -- only the raw-field MULTI-SELECT filters are dropped, per the
 * "drop a knob under ~40% populated, say so" rule. See the final report
 * for the exact numbers.
 */
'use strict';

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
    inRange,
    applyFilters,
    DEFAULT_FILTER_STATE,
  };
}
