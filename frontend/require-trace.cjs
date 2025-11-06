(function(){
  if (global.__require_trace_installed) return;
  global.__require_trace_installed = true;

  const fs = require('fs');
  const path = require('path');
  const Module = require('module');

  const LOG = path.join(__dirname, 'require-trace.log');
  try {
    fs.writeFileSync(LOG, `--- require trace start ${new Date().toISOString()}\n`);
  } catch (err) {
    // ignore
  }

  const origLoad = Module._load;
  Module._load = function(request, parent, isMain) {
    try {
      const suspect = new RegExp('(@vitest|@testing-library|vitest|jest-dom|@vitest/expect|jest-dom|\\bexpect\\b)', 'i');
      if (suspect.test(String(request)) || (parent && suspect.test(String(parent.filename || '')))) {
        const stack = new Error().stack || '';
        const entry = `[${new Date().toISOString()}] require(${JSON.stringify(request)}) from ${parent && parent.filename}\n${stack}\n\n`;
        try { fs.appendFileSync(LOG, entry); } catch (e) {}
        try { console.error('[require-trace]', request, 'from', parent && parent.filename); } catch (e) {}
      }
    } catch (e) {
      // swallow tracing errors
    }
    return origLoad.apply(this, arguments);
  };

  // Also write a small note to stdout so it's obvious the tracer loaded
  try { console.error('[require-trace] tracer loaded'); } catch (e) {}
})();
// Lightweight require tracer preloaded via NODE_OPTIONS="--require ./require-trace.cjs"
// Logs module loads that mention vitest, @vitest, jest-dom, testing-library, or expect
const fs = require('fs');
const path = require('path');
const Module = require('module');

const LOG = path.join(__dirname, 'require-trace.log');
function append() {
  try {
    fs.appendFileSync(LOG, Array.from(arguments).join(' ') + '\n');
  } catch (err) {
    // ignore
  }
}

append('=== require-trace start ===', new Date().toISOString(), 'argv=' + process.argv.join(' '));

const origLoad = Module._load;
Module._load = function(request, parent /*, isMain */) {
  try {
    const req = String(request || '');
    const look = ['vitest', '@vitest', 'jest-dom', 'testing-library', 'expect', 'vitest.setup', 'vitest.config'];
    for (let i = 0; i < look.length; i++) {
      const token = look[i];
      if (req.includes(token)) {
        append('[LOAD]', token, '->', req, 'parent:', (parent && parent.id) ? parent.id : '<root>');
        break;
      }
    }
  } catch (e) {
    // swallow
  }
  return origLoad.apply(this, arguments);
};

append('require-trace installed');
