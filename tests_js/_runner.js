/*
 * Minimal, dependency-free test runner for this repo's Node tests. No
 * test framework (jest/mocha/etc) is installed anywhere in this repo and
 * this project's Node (v14) predates `node --test` (added in v18) -- a
 * few dozen lines here beat adding a new package-manager dependency just
 * for `describe`/`it`/matchers this suite doesn't otherwise need.
 *
 * Usage, from a test file:
 *   const { test, run } = require('./_runner');
 *   test('does a thing', () => { ... throw on failure (assert.*) ... });
 *   run(); // call once, at the end of the file
 */
'use strict';

const tests = [];

function test(name, fn) {
  tests.push({ name, fn });
}

function run() {
  let passed = 0;
  let failed = 0;
  for (const { name, fn } of tests) {
    try {
      fn();
      passed += 1;
      console.log(`  ok - ${name}`);
    } catch (err) {
      failed += 1;
      console.error(`  FAIL - ${name}`);
      console.error(`    ${err && err.message ? err.message : err}`);
    }
  }
  console.log(`${passed} passed, ${failed} failed`);
  if (failed > 0) {
    process.exitCode = 1;
  }
}

module.exports = { test, run };
