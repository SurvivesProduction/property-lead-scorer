'use strict';

const assert = require('assert');
const path = require('path');
const { test, run } = require('./_runner');
const { PRESETS } = require(path.join('..', 'lead_board', 'presets.js'));
const { computeScore } = require(path.join('..', 'lead_board', 'scoring.js'));

test('darren_default matches the real config weights (0.50/0.30/0.15/0.05)', () => {
  const { weights } = PRESETS.darren_default;
  assert.strictEqual(weights.property, 0.5);
  assert.strictEqual(weights.siding, 0.3);
  assert.strictEqual(weights.canopy, 0.15);
  assert.strictEqual(weights.storm, 0.05);
  assert.strictEqual(weights.jobSize, 0);
  assert.strictEqual(weights.saleRecency, 0);
});

test('siding_focused: siding is the heaviest weight', () => {
  const { weights } = PRESETS.siding_focused;
  const others = [weights.property, weights.canopy, weights.storm, weights.jobSize, weights.saleRecency];
  assert.ok(others.every((w) => w < weights.siding), 'siding must outweigh every other signal');
});

test('siding_focused: property weight is zero (2026-10-30 fix -- any property_weight > 0 re-pins the same ancient-durable-sided houses Darren default already surfaces, since durable siding saturates to the same 1.0 ceiling property age does)', () => {
  assert.strictEqual(PRESETS.siding_focused.weights.property, 0);
});

test('bigger_jobs: jobSize is meaningful and property age still matters (both >= 0.25)', () => {
  const { weights } = PRESETS.bigger_jobs;
  assert.ok(weights.jobSize >= 0.25, 'jobSize should be a real, non-token weight');
  assert.ok(weights.property >= 0.25, 'property age must still matter in this preset');
  assert.ok(weights.jobSize >= weights.siding, 'jobSize should be at least as prominent as siding in this preset');
});

test('every preset computes a well-formed score for a representative lead', () => {
  const components = { property: 0.7, canopy: 0.4, storm: 1.0, siding: 0.6, jobSize: 0.3, saleRecency: 0.5 };
  for (const key of Object.keys(PRESETS)) {
    const score = computeScore(components, PRESETS[key].weights);
    assert.ok(score >= 0 && score <= 1, `${key} produced an out-of-range score: ${score}`);
  }
});

run();
