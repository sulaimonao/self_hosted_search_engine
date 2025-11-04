import { expect, test } from '@playwright/test';

test.describe('render loop guard', () => {
  test('no render loop indicators on /browser', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') {
        errors.push(message.text());
      }
    });

    await page.goto(process.env.APP_BASE_URL ? `${process.env.APP_BASE_URL}/browser` : 'http://localhost:3100/browser', {
      waitUntil: 'networkidle',
    });
    await page.waitForTimeout(1500);

    const joined = errors.join('\n');
    expect.soft(joined).not.toMatch(/\[render-loop]/i);
    expect.soft(joined).not.toMatch(/maximum update depth exceeded/i);
  });
});
