'use strict';

const assert = require('assert');
const path = require('path');
const { test, run } = require('./_runner');
const { encodeState, decodeState, settingsToClipboardJson } = require(path.join('..', 'lead_board', 'state.js'));
const { DEFAULT_FILTER_STATE } = require(path.join('..', 'lead_board', 'filters.js'));
const { PRESETS } = require(path.join('..', 'lead_board', 'presets.js'));

function sampleState() {
  return Object.assign({}, DEFAULT_FILTER_STATE, {
    towns: new Set(['Killingly', 'Ashford']),
    sidingMaterials: new Set(['vinyl', 'durable_original']),
    roofCoverMaterials: new Set(['asphalt']),
    weights: PRESETS.siding_focused.weights,
    topN: 50,
  });
}

test('encodeState/decodeState round-trip: scalars and booleans survive exactly', () => {
  const state = sampleState();
  const decoded = decodeState(encodeState(state));
  assert.strictEqual(decoded.hideClaimed, state.hideClaimed);
  assert.strictEqual(decoded.hideWorked, state.hideWorked);
  assert.strictEqual(decoded.showStateOnly, state.showStateOnly);
  assert.strictEqual(decoded.topN, 50);
  assert.deepStrictEqual(decoded.weights, PRESETS.siding_focused.weights);
});

test('encodeState/decodeState round-trip: towns Set survives as a Set with the same members', () => {
  const state = sampleState();
  const decoded = decodeState(encodeState(state));
  assert.ok(decoded.towns instanceof Set);
  assert.deepStrictEqual(Array.from(decoded.towns).sort(), ['Ashford', 'Killingly']);
});

test('encodeState/decodeState round-trip: sidingMaterials/roofCoverMaterials Sets survive too', () => {
  const state = sampleState();
  const decoded = decodeState(encodeState(state));
  assert.ok(decoded.sidingMaterials instanceof Set);
  assert.deepStrictEqual(Array.from(decoded.sidingMaterials).sort(), ['durable_original', 'vinyl']);
  assert.ok(decoded.roofCoverMaterials instanceof Set);
  assert.deepStrictEqual(Array.from(decoded.roofCoverMaterials), ['asphalt']);
});

test('encodeState: produces a URL-hash-safe string (no +, /, =, #)', () => {
  const encoded = encodeState(sampleState());
  assert.ok(!/[+/=#]/.test(encoded), `hash contains unsafe characters: ${encoded}`);
});

test('decodeState: a garbage hash returns null rather than throwing', () => {
  assert.strictEqual(decodeState('not-valid-base64-json!!!'), null);
});

test('decodeState: towns stays null when the state had no town filter set', () => {
  const state = Object.assign({}, DEFAULT_FILTER_STATE, { towns: null });
  const decoded = decodeState(encodeState(state));
  assert.strictEqual(decoded.towns, null);
});

test('settingsToClipboardJson: valid JSON, same shape encodeState hashes', () => {
  const state = sampleState();
  const json = settingsToClipboardJson(state);
  const parsed = JSON.parse(json);
  assert.deepStrictEqual(parsed.towns, ['Ashford', 'Killingly']);
  assert.deepStrictEqual(parsed.weights, PRESETS.siding_focused.weights);
});

run();
