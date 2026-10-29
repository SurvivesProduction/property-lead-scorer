'use strict';

const assert = require('assert');
const path = require('path');
const { test, run } = require('./_runner');
const {
  isClaimedTerritory,
  isWorked,
  isMailedOrShown,
  isUnreachable,
  isStateOnly,
  hasRealPermitHistory,
  applyFilters,
  DEFAULT_FILTER_STATE,
} = require(path.join('..', 'lead_board', 'filters.js'));

function parcel(overrides) {
  return Object.assign(
    {
      town: 'Canterbury',
      year_built: 1950,
      pct_tree_canopy_nearby: 40,
      lead_key: 'Canterbury:1',
      flags: {
        permit_data_available: false,
        permit_history_short: false,
        is_absentee: false,
        is_delinquent: false,
        pipeline_status: null,
        mailed_or_shown: false,
        is_state_only: false,
      },
    },
    overrides,
    { flags: Object.assign({}, { permit_data_available: false, permit_history_short: false, is_absentee: false, is_delinquent: false, pipeline_status: null, mailed_or_shown: false, is_state_only: false }, overrides && overrides.flags) }
  );
}

test('isClaimedTerritory: case-insensitive match against sold_towns', () => {
  assert.strictEqual(isClaimedTerritory(parcel({ town: 'killingly' }), ['Killingly', 'Ashford']), true);
  assert.strictEqual(isClaimedTerritory(parcel({ town: 'Canterbury' }), ['Killingly', 'Ashford']), false);
});

test('isWorked: no pipeline row at all is unworked', () => {
  assert.strictEqual(isWorked(parcel({ flags: { pipeline_status: null } })), false);
});

test("isWorked: status 'new' is unworked", () => {
  assert.strictEqual(isWorked(parcel({ flags: { pipeline_status: 'new' } })), false);
});

test("isWorked: any non-'new' status is worked", () => {
  assert.strictEqual(isWorked(parcel({ flags: { pipeline_status: 'estimate booked' } })), true);
  assert.strictEqual(isWorked(parcel({ flags: { pipeline_status: 'not interested' } })), true);
});

test('isMailedOrShown / isUnreachable / isStateOnly read their own flag', () => {
  assert.strictEqual(isMailedOrShown(parcel({ flags: { mailed_or_shown: true } })), true);
  assert.strictEqual(isUnreachable(parcel({ flags: { is_absentee: true } })), true);
  assert.strictEqual(isUnreachable(parcel({ flags: { is_delinquent: true } })), true);
  assert.strictEqual(isStateOnly(parcel({ flags: { is_state_only: true } })), true);
});

test('hasRealPermitHistory: true only when available AND not short', () => {
  assert.strictEqual(
    hasRealPermitHistory(parcel({ flags: { permit_data_available: true, permit_history_short: false } })),
    true
  );
  assert.strictEqual(
    hasRealPermitHistory(parcel({ flags: { permit_data_available: true, permit_history_short: true } })),
    false,
    'Windham-shaped row (permit visible but short history) must never read as real permit history'
  );
  assert.strictEqual(
    hasRealPermitHistory(parcel({ flags: { permit_data_available: false, permit_history_short: false } })),
    false
  );
});

test('applyFilters default state: hides claimed/worked/mailed/unreachable/state-only', () => {
  const parcels = [
    parcel({ lead_key: 'claimed', town: 'Killingly' }),
    parcel({ lead_key: 'worked', flags: { pipeline_status: 'estimate booked' } }),
    parcel({ lead_key: 'mailed', flags: { mailed_or_shown: true } }),
    parcel({ lead_key: 'unreachable', flags: { is_absentee: true } }),
    parcel({ lead_key: 'state_only', flags: { is_state_only: true } }),
    parcel({ lead_key: 'survivor' }),
  ];
  const result = applyFilters(parcels, DEFAULT_FILTER_STATE, ['Killingly'], new Map());
  assert.deepStrictEqual(result.map((p) => p.lead_key), ['survivor']);
});

test('applyFilters: showStateOnly=true includes state-only rows', () => {
  const parcels = [parcel({ lead_key: 'state_only', flags: { is_state_only: true } })];
  const state = Object.assign({}, DEFAULT_FILTER_STATE, { showStateOnly: true, hideClaimed: false, hideWorked: false, hideMailed: false, hideUnreachable: false });
  const result = applyFilters(parcels, state, [], new Map());
  assert.strictEqual(result.length, 1);
});

test('applyFilters: town chip filter restricts to the selected towns', () => {
  const parcels = [parcel({ lead_key: 'a', town: 'Canterbury' }), parcel({ lead_key: 'b', town: 'Pomfret' })];
  const state = Object.assign({}, DEFAULT_FILTER_STATE, {
    towns: new Set(['Pomfret']),
    hideClaimed: false,
    hideWorked: false,
    hideMailed: false,
    hideUnreachable: false,
  });
  const result = applyFilters(parcels, state, [], new Map());
  assert.deepStrictEqual(result.map((p) => p.lead_key), ['b']);
});

test('applyFilters: year-built range excludes out-of-range parcels, passes unknowns through', () => {
  const parcels = [
    parcel({ lead_key: 'old', year_built: 1800 }),
    parcel({ lead_key: 'new', year_built: 2020 }),
    parcel({ lead_key: 'unknown', year_built: null }),
  ];
  const state = Object.assign({}, DEFAULT_FILTER_STATE, {
    yearBuiltMin: 1900,
    yearBuiltMax: 2000,
    hideClaimed: false,
    hideWorked: false,
    hideMailed: false,
    hideUnreachable: false,
  });
  const result = applyFilters(parcels, state, [], new Map());
  assert.deepStrictEqual(result.map((p) => p.lead_key), ['unknown']);
});

test('applyFilters: requireRealPermitHistory excludes a Windham-shaped (short-history) row', () => {
  const parcels = [
    parcel({ lead_key: 'windham_shaped', flags: { permit_data_available: true, permit_history_short: true } }),
    parcel({ lead_key: 'real_history', flags: { permit_data_available: true, permit_history_short: false } }),
  ];
  const state = Object.assign({}, DEFAULT_FILTER_STATE, {
    requireRealPermitHistory: true,
    hideClaimed: false,
    hideWorked: false,
    hideMailed: false,
    hideUnreachable: false,
  });
  const result = applyFilters(parcels, state, [], new Map());
  assert.deepStrictEqual(result.map((p) => p.lead_key), ['real_history']);
});

test('applyFilters: job-size percentile range filter', () => {
  const parcels = [parcel({ lead_key: 'small' }), parcel({ lead_key: 'big' })];
  const jobSize = new Map([['small', 0.1], ['big', 0.9]]);
  const state = Object.assign({}, DEFAULT_FILTER_STATE, {
    jobSizePctMin: 50,
    jobSizePctMax: 100,
    hideClaimed: false,
    hideWorked: false,
    hideMailed: false,
    hideUnreachable: false,
  });
  const result = applyFilters(parcels, state, [], jobSize);
  assert.deepStrictEqual(result.map((p) => p.lead_key), ['big']);
});

run();
