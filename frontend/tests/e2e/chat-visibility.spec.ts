import { test, expect } from '@playwright/test';

async function setRendererMode(page, mode: 'useChat' | 'manual') {
  await page.addInitScript((value) => {
    try { localStorage.setItem('chat:renderer', value); } catch {}
  }, mode);
}

async function sendPrompt(page, text: string) {
  await page.goto('/chat', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('textarea');
  await page.fill('textarea', text);
  await page.getByRole('button', { name: /send/i }).click();
}

test('chat messages visible with useChat renderer', async ({ page }) => {
  await setRendererMode(page, 'useChat');
  const prompt = 'Hello from e2e';
  await sendPrompt(page, prompt);

  // User echo should appear
  await expect(page.getByText(prompt, { exact: false })).toBeVisible();

  // Assistant should eventually stream some non-empty text (best-effort)
  await page.waitForTimeout(300); // small settle
  await page.waitForFunction(() => {
    const nodes = Array.from(document.querySelectorAll('div.bg-card.rounded-lg.border'));
    // Find any assistant card whose content area has non-empty text other than labels
    return nodes.some((el) => {
      const text = el.textContent || '';
      const simplified = text.replace(/\bassistant\b/i, '').replace(/Generating…/g, '').trim();
      return simplified.length > 0;
    });
  }, { timeout: 10000 });
});

test('chat messages visible with manual renderer', async ({ page }) => {
  await setRendererMode(page, 'manual');
  const prompt = 'Hello from manual';
  await sendPrompt(page, prompt);

  await expect(page.getByText(prompt, { exact: false })).toBeVisible();

  await page.waitForTimeout(300);
  await page.waitForFunction(() => {
    const nodes = Array.from(document.querySelectorAll('div.bg-card.rounded-lg.border'));
    const ok = nodes.some((el) => {
      const text = el.textContent || '';
      const simplified = text.replace(/\bassistant\b/i, '').replace(/Generating…/g, '').trim();
      return simplified.length > 0;
    });
    return ok;
  }, { timeout: 10000 });
});
