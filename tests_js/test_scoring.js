'use strict';

const assert = require('assert');
const path = require('path');
const { test, run } = require('./_runner');
const {
  computeScore,
  percentileRank,
  computeJobSizeComponent,
  computeSaleRecencyComponent,
  compareLeadsDesc,
  rankLeads,
} = require(path.join('..', 'lead_board', 'scoring.js'));

test('computeScore: weighted average of present components only', () => {
  const score = computeScore(
    { property: 0.8, canopy: 0.4, storm: 1.0, siding: 0.6 },
    { property: 0.5, canopy: 0.15, storm: 0.05, siding: 0.3 }
  );
  const expected = (0.5 * 0.8 + 0.15 * 0.4 + 0.05 * 1.0 + 0.3 * 0.6) / (0.5 + 0.15 + 0.05 + 0.3);
  assert.ok(Math.abs(score - expected) < 1e-12, `${score} !== ${expected}`);
});

test('computeScore: a null component is skipped, its weight excluded from the denominator', () => {
  const score = computeScore(
    { property: 0.8, canopy: 0.4, storm: 1.0, siding: null },
    { property: 0.5, canopy: 0.15, storm: 0.05, siding: 0.3 }
  );
  const expected = (0.5 * 0.8 + 0.15 * 0.4 + 0.05 * 1.0) / (0.5 + 0.15 + 0.05);
  assert.ok(Math.abs(score - expected) < 1e-12);
});

test('computeScore: a zero weight on a present component is a no-op (matches Python)', () => {
  const withZero = computeScore(
    { property: 0.8, canopy: 0.4, storm: 1.0, siding: 0.6 },
    { property: 0.5, canopy: 0.15, storm: 0.05, siding: 0 }
  );
  const withoutSiding = computeScore(
    { property: 0.8, canopy: 0.4, storm: 1.0 },
    { property: 0.5, canopy: 0.15, storm: 0.05 }
  );
  assert.ok(Math.abs(withZero - withoutSiding) < 1e-12);
});

test('computeScore: all weights zero returns 0 (no division by zero)', () => {
  const score = computeScore({ property: 0.8 }, { property: 0 });
  assert.strictEqual(score, 0);
});

test('percentileRank: known values spread 0-1, largest value ranks highest', () => {
  const sorted = [10, 20, 30, 40, 50];
  assert.strictEqual(percentileRank(sorted, 50), 1);
  assert.ok(percentileRank(sorted, 10) < percentileRank(sorted, 50));
});

test('percentileRank: ties share the same (highest) rank', () => {
  const sorted = [10, 20, 20, 20, 50];
  assert.strictEqual(percentileRank(sorted, 20), 4 / 5);
});

test('percentileRank: null/undefined value returns null (never fabricated)', () => {
  assert.strictEqual(percentileRank([1, 2, 3], null), null);
  assert.strictEqual(percentileRank([1, 2, 3], undefined), null);
});

test('computeJobSizeComponent: falls back to assessed_value when sqft is unknown', () => {
  const sortedSqft = [1000, 2000, 3000];
  const sortedValue = [100000, 200000, 300000];
  const component = computeJobSizeComponent(
    { living_area_sqft: null, assessed_value: 300000 },
    sortedSqft,
    sortedValue
  );
  assert.strictEqual(component, 1);
});

test('computeJobSizeComponent: neutral 0.5 when both sqft and assessed_value are unknown', () => {
  const component = computeJobSizeComponent({ living_area_sqft: null, assessed_value: null }, [1, 2], [1, 2]);
  assert.strictEqual(component, 0.5);
});

test('computeSaleRecencyComponent: least-recently-sold scores highest (1 - rank)', () => {
  const sortedYears = [1990, 2000, 2010, 2020];
  const oldSale = computeSaleRecencyComponent({ last_sale_year: 1990 }, sortedYears);
  const newSale = computeSaleRecencyComponent({ last_sale_year: 2020 }, sortedYears);
  assert.ok(oldSale > newSale);
});

test('computeSaleRecencyComponent: neutral 0.5 when last_sale_year is unknown', () => {
  const component = computeSaleRecencyComponent({ last_sale_year: null }, [1990, 2000]);
  assert.strictEqual(component, 0.5);
});

test('compareLeadsDesc: higher score sorts first', () => {
  const a = { score: 0.9, living_area_sqft: 1000, year_built: 1950, parcel_id: '1' };
  const b = { score: 0.5, living_area_sqft: 2000, year_built: 1900, parcel_id: '2' };
  assert.ok(compareLeadsDesc(a, b) < 0);
});

test('compareLeadsDesc tiebreak: equal score, larger living_area_sqft first', () => {
  const a = { score: 0.5, living_area_sqft: 2000, year_built: 1950, parcel_id: '1' };
  const b = { score: 0.5, living_area_sqft: 1000, year_built: 1950, parcel_id: '2' };
  assert.ok(compareLeadsDesc(a, b) < 0);
});

test('compareLeadsDesc tiebreak: equal score+sqft, OLDER (smaller) year_built first', () => {
  const a = { score: 0.5, living_area_sqft: 1000, year_built: 1900, parcel_id: '1' };
  const b = { score: 0.5, living_area_sqft: 1000, year_built: 1950, parcel_id: '2' };
  assert.ok(compareLeadsDesc(a, b) < 0);
});

test('compareLeadsDesc tiebreak: equal score+sqft+year, LARGER parcel_id first (reversed order)', () => {
  const a = { score: 0.5, living_area_sqft: 1000, year_built: 1950, parcel_id: '999' };
  const b = { score: 0.5, living_area_sqft: 1000, year_built: 1950, parcel_id: '042' };
  assert.ok(compareLeadsDesc(a, b) < 0, 'expected the lexicographically larger parcel_id to sort first');
});

test('compareLeadsDesc tiebreak: missing living_area_sqft treated as 0, missing year_built as 0', () => {
  const withSqft = { score: 0.5, living_area_sqft: 1, year_built: null, parcel_id: '1' };
  const withoutSqft = { score: 0.5, living_area_sqft: null, year_built: null, parcel_id: '2' };
  assert.ok(compareLeadsDesc(withSqft, withoutSqft) < 0);
});

test('rankLeads: assigns 1-based rank in sorted order and leaves input array untouched', () => {
  const parcels = [
    { lead_key: 'A', town: 'X', year_built: 1950, living_area_sqft: 1000, parcel_id: '1', components: { property: 0.9, canopy: 0.5, storm: 1.0, siding: 0.5 } },
    { lead_key: 'B', town: 'X', year_built: 1950, living_area_sqft: 1000, parcel_id: '2', components: { property: 0.1, canopy: 0.5, storm: 1.0, siding: 0.5 } },
  ];
  const weights = { property: 0.5, canopy: 0.15, storm: 0.05, siding: 0.3, jobSize: 0, saleRecency: 0 };
  const ranked = rankLeads(parcels, weights, new Map(), new Map());
  assert.strictEqual(ranked[0].lead_key, 'A');
  assert.strictEqual(ranked[0].rank, 1);
  assert.strictEqual(ranked[1].rank, 2);
  assert.strictEqual(parcels[0].rank, undefined, 'rankLeads must not mutate its input');
});

test('rankLeads: default weight 0 on jobSize/saleRecency leaves the default ranking unchanged', () => {
  const parcels = [
    { lead_key: 'A', town: 'X', year_built: 1950, living_area_sqft: 1000, parcel_id: '1', components: { property: 0.9, canopy: 0.5, storm: 1.0, siding: 0.5 } },
    { lead_key: 'B', town: 'X', year_built: 1950, living_area_sqft: 1000, parcel_id: '2', components: { property: 0.1, canopy: 0.5, storm: 1.0, siding: 0.5 } },
  ];
  const weights = { property: 0.5, canopy: 0.15, storm: 0.05, siding: 0.3, jobSize: 0, saleRecency: 0 };
  // Wildly different job-size/sale-recency components -- at weight 0 they must have zero effect.
  const jobSize = new Map([['A', 0.01], ['B', 0.99]]);
  const saleRecency = new Map([['A', 0.01], ['B', 0.99]]);
  const ranked = rankLeads(parcels, weights, jobSize, saleRecency);
  assert.strictEqual(ranked[0].lead_key, 'A');
});

run();
