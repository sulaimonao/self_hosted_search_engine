/* eslint-disable */
// Lightweight require tracer preloaded via NODE_OPTIONS="--require ./require-trace.js"
// Logs module loads that mention vitest, @vitest, jest-dom, testing-library, or expect
const fs = require('fs');
const path = require('path');
const Module = require('module');

const LOG = path.join(__dirname, 'require-trace.log');
function append(...parts) {
  try {
    fs.appendFileSync(LOG, parts.join(' ') + '\n');
  } catch (e) {
    // ignore
  }
}

append('=== require-trace start ===', new Date().toISOString(), 'argv=' + process.argv.join(' '));

const origLoad = Module._load;
Module._load = function(request, parent, isMain) {
  try {
    const req = String(request || '');
    const look = ['vitest', '@vitest', 'jest-dom', 'testing-library', 'expect', 'vitest.setup', 'vitest.config'];
    for (const token of look) {
      if (req.includes(token)) {
        append('[LOAD]', token, '->', req, 'parent:', parent && parent.id ? parent.id : '<root>');
        break;
      }
    }
  } catch (e) {
    // swallow
  }
  return origLoad.apply(this, arguments);
};

// Also instrument require.extensions for .ts/.tsx if present (for older setups)
append('require-trace installed');
