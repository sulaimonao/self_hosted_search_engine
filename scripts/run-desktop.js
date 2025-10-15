#!/usr/bin/env node

/**
 * Orchestrates the desktop runtime by launching the production Next.js server
 * from the frontend workspace and starting the Electron shell once the UI is
 * reachable. The script ensures clean shutdown semantics so that Ctrl+C or
 * process exits tear down both child processes.
 */

const { spawn } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');
const waitOn = require('wait-on');

const repoRoot = path.resolve(__dirname, '..');
const frontendDir = path.join(repoRoot, 'frontend');
const electronEntry = path.join(repoRoot, 'electron', 'main.js');
const electronBin = path.join(
  repoRoot,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'electron.cmd' : 'electron',
);
const nextBuildSentinel = path.join(frontendDir, '.next', 'BUILD_ID');

if (!fs.existsSync(electronBin)) {
  console.error('[desktop] Electron binary not found. Did you run `npm install`?');
  process.exit(1);
}

const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const browserRoute = process.env.DESKTOP_BROWSER_ROUTE || '/browser';
const normalizedRoute = browserRoute.startsWith('/') ? browserRoute : `/${browserRoute}`;
const waitTimeoutMs = Number(process.env.DESKTOP_WAIT_TIMEOUT_MS) || 60000;

let nextProcess;
let electronProcess;
let shuttingDown = false;
let port;
let frontendUrl;
let waitResource;

function ensureNextBuild() {
  if (process.env.DESKTOP_SKIP_BUILD_CHECK === '1') {
    return;
  }
  if (fs.existsSync(nextBuildSentinel)) {
    return;
  }
  console.error('[desktop] No Next.js production build detected.');
  console.error(
    '[desktop] Run `npm --prefix frontend run build:web` before `npm run desktop`, ' +
      'or set DESKTOP_SKIP_BUILD_CHECK=1 to bypass this check.',
  );
  process.exit(1);
}

function sanitizeBaseUrl(value) {
  return value ? value.replace(/\/$/, '') : value;
}

function parsePort(value) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > 65535) {
    throw new Error(`Invalid port value: ${value}`);
  }
  return parsed;
}

async function isPortAvailable(candidatePort) {
  return new Promise((resolve, reject) => {
    const tester = net.createServer();
    tester.unref();

    tester.once('error', (error) => {
      if (error && (error.code === 'EADDRINUSE' || error.code === 'EACCES')) {
        resolve(false);
        return;
      }
      reject(error);
    });

    tester.once('listening', () => {
      tester.close(() => {
        resolve(true);
      });
    });

    tester.listen({ port: candidatePort, host: '127.0.0.1' });
  });
}

async function resolvePort(preferredPort, { allowFallback }) {
  const startPort = parsePort(preferredPort);
  const maxOffset = allowFallback ? 100 : 0;

  for (let offset = 0; offset <= maxOffset; offset += 1) {
    const candidate = startPort + offset;
    // Clamp to valid range before probing.
    if (candidate > 65535) {
      break;
    }
    // eslint-disable-next-line no-await-in-loop
    const available = await isPortAvailable(candidate);
    if (available) {
      return candidate;
    }
  }

  if (allowFallback) {
    throw new Error(
      `Unable to find a free port starting at ${startPort}. ` +
        'Set DESKTOP_PORT or PORT to an available port and try again.',
    );
  }

  throw new Error(`Requested port ${startPort} is already in use.`);
}

async function resolveConfiguration() {
  const explicitPort = [process.env.PORT, process.env.DESKTOP_PORT].find(
    (value) => typeof value === 'string' && value.trim() !== '',
  );
  const preferredPort = explicitPort || '3100';

  const resolvedPortNumber = await resolvePort(preferredPort, {
    allowFallback: !explicitPort,
  }).catch((error) => {
    console.error('[desktop] Failed to resolve port configuration:', error.message || error);
    throw error;
  });

  if (!explicitPort && String(resolvedPortNumber) !== String(preferredPort)) {
    console.log(
      `[desktop] Port ${preferredPort} unavailable, using ${resolvedPortNumber} instead.`,
    );
  }

  port = String(resolvedPortNumber);
  process.env.PORT = port;

  const baseOverride = process.env.DESKTOP_FRONTEND_BASE;
  const normalizedBase = sanitizeBaseUrl(baseOverride || `http://127.0.0.1:${port}`);

  const defaultRouteUrl = `${normalizedBase}${normalizedRoute}`;
  frontendUrl = process.env.FRONTEND_URL || defaultRouteUrl;
  waitResource = process.env.DESKTOP_WAIT_RESOURCE || defaultRouteUrl;
}

function spawnProcess(command, args, options = {}) {
  const { env: envOverrides = {}, ...rest } = options;
  return spawn(command, args, {
    stdio: 'inherit',
    cwd: repoRoot,
    env: {
      ...process.env,
      PORT: port,
      NODE_ENV: process.env.NODE_ENV || 'production',
      ...envOverrides,
    },
    ...rest,
  });
}

function gracefulShutdown(exitCode = 0) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;

  const children = [electronProcess, nextProcess].filter(Boolean);
  if (children.length === 0) {
    process.exit(exitCode);
    return;
  }

  Promise.all(
    children.map(
      (child) =>
        new Promise((resolve) => {
          if (!child || child.killed) {
            resolve();
            return;
          }
          child.once('close', resolve);
          child.kill();
        }),
    ),
  )
    .catch(() => {})
    .finally(() => {
      process.exit(exitCode);
    });
}

process.on('SIGINT', () => {
  console.log('\n[desktop] Caught SIGINT, shutting down…');
  gracefulShutdown(0);
});

process.on('SIGTERM', () => {
  console.log('\n[desktop] Caught SIGTERM, shutting down…');
  gracefulShutdown(0);
});

async function waitForFrontend() {
  const resource = waitResource.startsWith('http://') || waitResource.startsWith('https://')
    ? waitResource
    : `http-get://${waitResource}`;
  console.log(`[desktop] Waiting for frontend at ${resource} …`);

  await new Promise((resolve, reject) => {
    waitOn(
      {
        resources: [resource],
        timeout: waitTimeoutMs,
        interval: 250,
        tcpTimeout: 1000,
        httpTimeout: 1000,
        window: undefined,
      },
      (error) => {
        if (error) {
          reject(error);
        } else {
          resolve();
        }
      },
    );
  });
}

function startFrontend() {
  console.log('[desktop] Starting Next.js frontend…');
  nextProcess = spawnProcess(npmCmd, ['--prefix', frontendDir, 'run', 'start:web'], {
    env: {
      // Force the production Next.js server to listen on the loopback interface so that
      // both the readiness probe and Electron shell can reach it consistently.
      HOSTNAME: '127.0.0.1',
      HOST: '127.0.0.1',
    },
  });
  nextProcess.on('error', (error) => {
    if (shuttingDown) {
      return;
    }
    console.error('[desktop] Failed to launch Next.js process:', error);
    gracefulShutdown(1);
  });
  nextProcess.on('exit', (code, signal) => {
    if (shuttingDown) {
      return;
    }
    const reason = signal ? `signal ${signal}` : `code ${code}`;
    console.error(`[desktop] Next.js process exited unexpectedly (${reason}).`);
    gracefulShutdown(code === 0 ? 1 : code || 1);
  });
}

function startElectron() {
  console.log('[desktop] Starting Electron shell…');
  electronProcess = spawnProcess(
    electronBin,
    [electronEntry],
    {
      env: {
        FRONTEND_URL: frontendUrl,
      },
    },
  );
  electronProcess.on('error', (error) => {
    if (shuttingDown) {
      return;
    }
    console.error('[desktop] Failed to launch Electron:', error);
    gracefulShutdown(1);
  });
  electronProcess.on('exit', (code, signal) => {
    if (shuttingDown) {
      return;
    }
    const reason = signal ? `signal ${signal}` : `code ${code}`;
    console.log(`[desktop] Electron exited (${reason}).`);
    gracefulShutdown(code || 0);
  });
}

async function main() {
  ensureNextBuild();
  await resolveConfiguration();
  startFrontend();

  try {
    await Promise.race([
      waitForFrontend(),
      new Promise((_, reject) => {
        nextProcess.once('exit', (code) => {
          reject(new Error(`Next.js exited with code ${code ?? 0} before serving UI`));
        });
      }),
    ]);
  } catch (error) {
    console.error('[desktop] Frontend did not become ready:', error?.message || error);
    gracefulShutdown(1);
    return;
  }

  if (shuttingDown) {
    return;
  }

  startElectron();
}

main().catch((error) => {
  console.error('[desktop] Unhandled error while starting desktop runtime:', error);
  gracefulShutdown(1);
});
