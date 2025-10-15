#!/usr/bin/env node

/**
 * Orchestrates the desktop runtime by launching the production Next.js server
 * from the frontend workspace and starting the Electron shell once the UI is
 * reachable. The script ensures clean shutdown semantics so that Ctrl+C or
 * process exits tear down both child processes.
 */

const { spawn } = require('node:child_process');
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

if (!fs.existsSync(electronBin)) {
  console.error('[desktop] Electron binary not found. Did you run `npm install`?');
  process.exit(1);
}

const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const port = String(process.env.PORT || process.env.DESKTOP_PORT || '3100');
const browserRoute = process.env.DESKTOP_BROWSER_ROUTE || '/browser';
const normalizedRoute = browserRoute.startsWith('/') ? browserRoute : `/${browserRoute}`;
const frontendBase = process.env.DESKTOP_FRONTEND_BASE || `http://127.0.0.1:${port}`;
const frontendUrl = process.env.FRONTEND_URL || `${frontendBase.replace(/\/$/, '')}${normalizedRoute}`;
const waitResource = process.env.DESKTOP_WAIT_RESOURCE || `${frontendBase.replace(/\/$/, '')}${normalizedRoute}`;
const waitTimeoutMs = Number(process.env.DESKTOP_WAIT_TIMEOUT_MS) || 60000;

let nextProcess;
let electronProcess;
let shuttingDown = false;

function spawnProcess(command, args, options = {}) {
  return spawn(command, args, {
    stdio: 'inherit',
    cwd: repoRoot,
    env: {
      ...process.env,
      PORT: port,
      NODE_ENV: process.env.NODE_ENV || 'production',
      ...options.env,
    },
    ...options,
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
  nextProcess = spawnProcess(npmCmd, ['--prefix', frontendDir, 'run', 'start:web']);
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
