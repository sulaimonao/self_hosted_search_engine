import { chromium } from 'playwright';
import http from 'node:http';

function resolveBaseUrl() {
  const fromEnv = process.env.PLAYWRIGHT_APP_URL || process.env.RENDERER_URL;
  if (typeof fromEnv === 'string' && fromEnv.trim()) return fromEnv.trim().replace(/\/$/, '');
  return 'http://127.0.0.1:3100';
}

async function waitForServer(url, timeout = 30000, interval = 500) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      await new Promise((res, rej) => {
        const req = http.get(url, (r) => {
          r.resume();
          res();
        });
        req.on('error', rej);
        req.setTimeout(3000, () => req.destroy(new Error('timeout')));
      });
      return true;
    } catch {
  await new Promise((r) => setTimeout(r, interval));
    }
  }
  return false;
}

(async () => {
  const baseUrl = resolveBaseUrl();
  const serverReady = await waitForServer(baseUrl);
  if (!serverReady) {
    console.error('Server not ready at', baseUrl);
    process.exitCode = 4;
    return;
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('console', (msg) => {
    try {
      if (msg.type && msg.type() === 'error') errors.push(msg.text());
    } catch {
      // ignore
    }
  });

  try {
    await page.goto(`${baseUrl}/browser`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    await page.goto(`${baseUrl}/chat`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);

    const joined = errors.join('\n');
    if (joined.includes('[render-loop]') || /Maximum update depth exceeded/.test(joined)) {
      console.error('Render loop detected:', joined);
      await browser.close();
      process.exitCode = 2;
      return;
    }

    console.log('Render-loop smoke passed');
    await browser.close();
    process.exitCode = 0;
  } catch (err) {
    console.error('Smoke script failed', String(err));
    try { await browser.close(); } catch {}
    process.exitCode = 3;
  }
})();
