import { test, expect } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:5050';

test.beforeEach(async ({ request }) => {
  const response = await request.put(`${apiBase}/api/config`, {
    data: { setup_completed: true },
  });
  if (!response.ok()) {
    throw new Error(`Failed to prime setup state (${response.status()})`);
  }
});

async function setRendererMode(page, mode: 'useChat' | 'manual') {
  await page.addInitScript((value) => {
    try { localStorage.setItem('chat:renderer', value); } catch {}
  }, mode);
}

async function dismissFirstRunWizardIfPresent(page) {
  const skipButton = page.getByRole('button', { name: /skip for now/i });
  try {
    await skipButton.first().click({ timeout: 30_000 });
    await skipButton.first().waitFor({ state: 'detached', timeout: 5_000 });
  } catch {
    // Wizard not present or already dismissed.
  }
}

async function openChatPanel(page) {
  await page.goto('/browser', { waitUntil: 'domcontentloaded' });
  await dismissFirstRunWizardIfPresent(page);
  // Prefer the accessible name lookup; if the button is temporarily
  // hidden behind an aria-hidden wrapper, fall back to the aria-label
  // locator once the wrapper is removed.
  let chatButton = page.getByRole('button', { name: /open chat panel/i });
  try {
    await chatButton.first().waitFor({ state: 'visible', timeout: 5_000 });
  } catch {
    chatButton = page.locator('[aria-label="Open chat panel"]');
    await page.waitForFunction(() => {
      const target = document.querySelector('[aria-label="Open chat panel"]');
      if (!target) return false;
      return !target.closest('[aria-hidden="true"]');
    });
  }
  await chatButton.first().click();
  await page.waitForSelector('textarea');
}

async function sendPrompt(page, text: string) {
  await openChatPanel(page);
  await page.fill('textarea', text);
  await page.getByRole('button', { name: /send/i }).click();
}

test('chat messages visible with useChat renderer', async ({ page }) => {
  await setRendererMode(page, 'useChat');
  const prompt = 'Hello from e2e';
  await sendPrompt(page, prompt);

  // User echo should appear
  await expect(page.locator('p', { hasText: prompt }).first()).toBeVisible();

  // Assistant placeholder/spinner should appear even if backend is slow or offline
  await expect(page.getByText('Generating…')).toBeVisible({ timeout: 15000 });
});

test('chat messages visible with manual renderer', async ({ page }) => {
  await setRendererMode(page, 'manual');
  const prompt = 'Hello from manual';
  await sendPrompt(page, prompt);
  // User echo should appear
  await expect(page.locator('p', { hasText: prompt }).first()).toBeVisible();

  // Assistant feedback: either a spinner or an error message, depending
  // on whether the backend can stream successfully.
  const spinner = page.getByText('Generating…');
  const errorText = page.getByText(/Error:/);

  await Promise.race([
    spinner.waitFor({ state: 'visible', timeout: 15_000 }),
    errorText.waitFor({ state: 'visible', timeout: 15_000 }),
  ]);
});
