#!/usr/bin/env node

const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

const DEFAULT_TIMEOUT_MS = 30000;

function readTimeoutMs() {
  const raw = process.env.DIAG_TIMEOUT;
  if (!raw) {
    return DEFAULT_TIMEOUT_MS;
  }
  const value = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(value) || value <= 0) {
    return DEFAULT_TIMEOUT_MS;
  }
  return value;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowIso() {
  return new Date().toISOString();
}

function createRecorder() {
  const logs = [];
  const trace = [];
  const log = (level, message, data = null) => {
    logs.push({
      timestamp: nowIso(),
      level,
      message,
      data: data === undefined ? null : data,
    });
  };
  const record = (event) => {
    if (!event || typeof event !== 'object') {
      return;
    }
    trace.push({
      timestamp: nowIso(),
      ...event,
    });
  };
  return { logs, trace, log, record };
}

async function withWindow(options, task, recorder, context = {}) {
  const win = new BrowserWindow({
    show: false,
    width: 800,
    height: 600,
    webPreferences: {
      offscreen: true,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      ...options?.webPreferences,
    },
  });
  recorder?.record({ type: 'window:create', context });
  try {
    return await task(win);
  } finally {
    recorder?.record({ type: 'window:destroy', context });
    if (!win.isDestroyed()) {
      win.destroy();
    }
  }
}

async function loadUrl(win, url, { expectFailure = false, timeoutMs }, recorder, context = {}) {
  const startedAt = Date.now();
  return new Promise((resolve) => {
    let settled = false;
    const finish = (status) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const payload = { ...status, durationMs: Date.now() - startedAt };
      recorder?.record({
        type: 'load:complete',
        context,
        url,
        expectFailure,
        outcome: status.outcome,
        detail: status.detail ?? null,
        durationMs: payload.durationMs,
      });
      resolve(payload);
    };

    const effectiveTimeout = typeof timeoutMs === 'number' && Number.isFinite(timeoutMs) ? timeoutMs : DEFAULT_TIMEOUT_MS;
    const timer = setTimeout(() => {
      recorder?.record({ type: 'load:timeout', context, url, timeoutMs: effectiveTimeout });
      finish({ outcome: 'timeout', detail: `Timed out after ${effectiveTimeout}ms` });
    }, effectiveTimeout);

    recorder?.record({ type: 'load:start', context, url, expectFailure, timeoutMs: effectiveTimeout });
    win.webContents.once('did-finish-load', () => {
      if (expectFailure) {
        finish({ outcome: 'fail', detail: 'Page loaded but failure expected' });
      } else {
        finish({ outcome: 'pass' });
      }
    });

    win.webContents.once('did-fail-load', (_event, errorCode, errorDescription) => {
      if (expectFailure) {
        finish({ outcome: 'pass', detail: `${errorDescription || errorCode}` });
      } else {
        finish({ outcome: 'fail', detail: `${errorDescription || errorCode}` });
      }
    });

    win.loadURL(url).catch((error) => {
      recorder?.record({
        type: 'load:error',
        context,
        url,
        error: error?.message || 'loadURL failed',
      });
      finish({ outcome: 'fail', detail: error?.message || 'loadURL failed' });
    });
  });
}

async function checkTlsFailures(timeoutMs, recorder) {
  const targets = [
    { id: 'expired.badssl.com', label: 'Block expired certificate', critical: true },
    { id: 'wrong.host.badssl.com', label: 'Block wrong host certificate', critical: true },
    { id: 'self-signed.badssl.com', label: 'Block self-signed certificate', critical: true },
  ];

  const results = [];
  for (const target of targets) {
    const context = { checkId: target.id };
    recorder?.record({ type: 'check:start', id: target.id, title: target.label });
    const outcome = await withWindow(
      {},
      (win) => loadUrl(win, `https://${target.id}/`, { expectFailure: true, timeoutMs }, recorder, context),
      recorder,
      context,
    );
    results.push({
      id: target.id,
      title: target.label,
      status: outcome.outcome === 'pass' ? 'pass' : outcome.outcome,
      detail: outcome.detail ?? null,
      critical: target.critical,
      durationMs: outcome.durationMs ?? null,
    });
    recorder?.record({
      type: 'check:result',
      id: target.id,
      title: target.label,
      status: outcome.outcome === 'pass' ? 'pass' : outcome.outcome,
      detail: outcome.detail ?? null,
      durationMs: outcome.durationMs ?? null,
      critical: target.critical,
    });
    await delay(150);
  }
  return results;
}

async function checkBasicHttps(timeoutMs, recorder) {
  const context = { checkId: 'https-example' };
  recorder?.record({ type: 'check:start', id: 'https-example', title: 'Load https://example.com' });
  const outcome = await withWindow(
    {},
    (win) => loadUrl(win, 'https://example.com/', { expectFailure: false, timeoutMs }, recorder, context),
    recorder,
    context,
  );
  recorder?.record({
    type: 'check:result',
    id: 'https-example',
    title: 'Load https://example.com',
    status: outcome.outcome === 'pass' ? 'pass' : outcome.outcome,
    detail: outcome.detail ?? null,
    durationMs: outcome.durationMs ?? null,
    critical: false,
  });
  return {
    id: 'https-example',
    title: 'Load https://example.com',
    status: outcome.outcome === 'pass' ? 'pass' : outcome.outcome,
    detail: outcome.detail ?? null,
    critical: false,
    durationMs: outcome.durationMs ?? null,
  };
}

async function checkStorage(timeoutMs, recorder) {
  const url = 'https://example.com/';
  const context = { checkId: 'storage-basics' };
  recorder?.record({ type: 'check:start', id: 'storage-basics', title: 'Cookies and localStorage' });
  const result = await withWindow(
    { webPreferences: { partition: 'persist:diagnostics' } },
    async (win) => {
      const loadResult = await loadUrl(win, url, { expectFailure: false, timeoutMs }, recorder, context);
      if (loadResult.outcome !== 'pass') {
        return { status: loadResult.outcome, detail: loadResult.detail ?? null, durationMs: loadResult.durationMs ?? null };
      }
      try {
        const evaluation = await win.webContents.executeJavaScript(
          `(() => {
          try {
            const key = 'diagnostics-' + Date.now();
            localStorage.setItem(key, 'ok');
            const stored = localStorage.getItem(key);
            localStorage.removeItem(key);
            document.cookie = 'diag_cookie=1; SameSite=Lax';
            return { localStorage: stored === 'ok', cookie: document.cookie.includes('diag_cookie=1') };
          } catch (error) {
            return { error: error && error.message ? String(error.message) : 'storage error' };
          }
        })();`,
          true,
        );
        if (evaluation && typeof evaluation === 'object') {
          if (evaluation.error) {
            return { status: 'fail', detail: String(evaluation.error) };
          }
          if (evaluation.localStorage && evaluation.cookie) {
            return { status: 'pass' };
          }
          return {
            status: 'warn',
            detail: `Storage results: localStorage=${evaluation.localStorage}, cookie=${evaluation.cookie}`,
          };
        }
      } catch (error) {
        return { status: 'fail', detail: error?.message ?? 'executeJavaScript failed' };
      }
      return { status: 'warn', detail: 'No evaluation result' };
    },
    recorder,
    context,
  );
  recorder?.record({
    type: 'check:result',
    id: 'storage-basics',
    title: 'Cookies and localStorage',
    status: result.status,
    detail: result.detail ?? null,
    durationMs: result.durationMs ?? null,
    critical: false,
  });
  return {
    id: 'storage-basics',
    title: 'Cookies and localStorage',
    status: result.status,
    detail: result.detail ?? null,
    critical: false,
    durationMs: result.durationMs ?? null,
  };
}

async function checkServiceWorker(timeoutMs, recorder) {
  const url = 'https://mdn.github.io/dom-examples/service-worker/simple-service-worker/';
  const context = { checkId: 'service-worker' };
  recorder?.record({ type: 'check:start', id: 'service-worker', title: 'Service worker registration' });
  const result = await withWindow(
    {},
    async (win) => {
      const loadResult = await loadUrl(win, url, { expectFailure: false, timeoutMs }, recorder, context);
      if (loadResult.outcome !== 'pass') {
        return { status: loadResult.outcome, detail: loadResult.detail ?? null, durationMs: loadResult.durationMs ?? null };
      }
      try {
        const registration = await win.webContents.executeJavaScript(
          `navigator.serviceWorker.getRegistrations().then(list => ({ count: list.length }))`,
          true,
        );
        if (registration && typeof registration.count === 'number') {
          if (registration.count >= 1) {
            return { status: 'pass' };
          }
          return { status: 'warn', detail: 'No service workers registered' };
        }
        return { status: 'warn', detail: 'Unexpected registration result' };
      } catch (error) {
        return { status: 'fail', detail: error?.message ?? 'service worker query failed' };
      }
    },
    recorder,
    context,
  );
  recorder?.record({
    type: 'check:result',
    id: 'service-worker',
    title: 'Service worker registration',
    status: result.status,
    detail: result.detail ?? null,
    durationMs: result.durationMs ?? null,
    critical: false,
  });
  return {
    id: 'service-worker',
    title: 'Service worker registration',
    status: result.status,
    detail: result.detail ?? null,
    critical: false,
    durationMs: result.durationMs ?? null,
  };
}

function summarizeChecks(checks) {
  let criticalFailures = false;
  let status = 'pass';
  for (const check of checks) {
    if (check.status !== 'pass') {
      if (check.critical) {
        criticalFailures = true;
        status = 'fail';
        break;
      }
      if (status === 'pass') {
        status = check.status;
      }
    }
  }
  return { status, criticalFailures };
}

function writeReport(report) {
  try {
    const outputDir = path.resolve(__dirname, '..', 'diagnostics');
    fs.mkdirSync(outputDir, { recursive: true });
    const outputPath = path.join(outputDir, 'browser_diagnostics.json');
    fs.writeFileSync(outputPath, JSON.stringify(report, null, 2));
    return outputPath;
  } catch (error) {
    return null;
  }
}

async function runBrowserDiagnostics(options = {}) {
  const timeoutMs = options.timeoutMs ?? readTimeoutMs();
  if (!app.isReady()) {
    await app.whenReady();
  }

  const startedAt = Date.now();
  const recorder = createRecorder();
  recorder.log('info', 'Starting browser diagnostics', { timeoutMs });
  recorder.record({ type: 'diagnostics:start', timeoutMs });

  const checks = [];
  const httpsCheck = await checkBasicHttps(timeoutMs, recorder);
  checks.push(httpsCheck);
  const tlsChecks = await checkTlsFailures(timeoutMs, recorder);
  checks.push(...tlsChecks);
  const storageCheck = await checkStorage(timeoutMs, recorder);
  checks.push(storageCheck);
  const swCheck = await checkServiceWorker(timeoutMs, recorder);
  checks.push(swCheck);

  const summary = summarizeChecks(checks);
  recorder.record({
    type: 'diagnostics:summary',
    status: summary.status,
    criticalFailures: summary.criticalFailures,
  });

  const metadata = {
    electron: process.versions?.electron ?? null,
    chrome: process.versions?.chrome ?? null,
    node: process.versions?.node ?? null,
    platform: process.platform,
    arch: process.arch,
    release: os.release(),
    appVersion: typeof app.getVersion === 'function' ? app.getVersion() : null,
  };

  const finishedAt = Date.now();
  const report = {
    generatedAt: nowIso(),
    timeoutMs,
    checks,
    summary,
    durationMs: finishedAt - startedAt,
    trace: recorder.trace,
    logs: recorder.logs,
    metadata,
  };

  if (options.write !== false) {
    const artifactPath = writeReport(report);
    report.artifactPath = artifactPath ?? null;
  }

  if (options.log) {
    console.log(JSON.stringify(report));
  }

  return report;
}

if (require.main === module) {
  runBrowserDiagnostics({ log: true })
    .then(() => {
      app.exit(0);
    })
    .catch((error) => {
      console.error(JSON.stringify({ error: error?.message ?? String(error) }));
      app.exit(1);
    });
}

module.exports = { runBrowserDiagnostics };
