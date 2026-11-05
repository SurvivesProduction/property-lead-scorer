'use strict';
/* Runs every test_*.js file in this directory as its own process (so one
 * file's `process.exitCode` doesn't leak into the next) and aggregates
 * the result. Usage: `node tests_js/run_all.js`. */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const dir = __dirname;
const files = fs
  .readdirSync(dir)
  .filter((f) => f.startsWith('test_') && f.endsWith('.js'))
  .sort();

let anyFailed = false;
for (const file of files) {
  console.log(`\n== ${file} ==`);
  const result = spawnSync(process.execPath, [path.join(dir, file)], { stdio: 'inherit' });
  if (result.status !== 0) anyFailed = true;
}

process.exitCode = anyFailed ? 1 : 0;
