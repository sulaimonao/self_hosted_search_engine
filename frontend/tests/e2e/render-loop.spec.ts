import { test, expect } from '@playwright/test';

test('no render loop markers on /browser', async ({ page }) => {
  const hits: string[] = [];
  page.on('console', (msg) => {
    const t = msg.text();
    if (/hydration failed|Maximum update depth exceeded|render loop|update depth/i.test(t)) {
      hits.push(t);
    }
  });

  await page.goto('/browser', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(600);

  expect(hits.join('\n')).toBe('');
});

