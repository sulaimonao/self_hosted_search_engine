// @ts-expect-error playwright test types are provided at runtime in e2e environment
import { expect, test } from '@playwright/test';

test.describe('Control Center Roadmap', () => {
  test('loads roadmap panel and shows Run Diagnostics', async ({ page }: { page: any }) => {
    test.skip(process.env.CI === 'true', 'Roadmap UI e2e disabled on CI');

    const uiBase = process.env.UI_BASE_URL ?? 'http://127.0.0.1:3100';
    await page.goto(`${uiBase}/control-center/roadmap`);
    await expect(page.getByRole('heading', { name: 'Roadmap' })).toBeVisible();
    const runButton = page.getByRole('button', { name: /Run Diagnostics/i });
    await expect(runButton).toBeVisible();
  });
});
