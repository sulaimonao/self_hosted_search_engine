// @ts-expect-error playwright test types are provided at runtime in e2e environment
import { expect, test } from '@playwright/test';

test.describe('Control Center Roadmap', () => {
  test('loads roadmap panel and shows Run Diagnostics', async ({ page }: { page: any }) => {
    test.skip(process.env.CI === 'true', 'Roadmap UI e2e disabled on CI');

    const uiBase = process.env.UI_BASE_URL ?? 'http://127.0.0.1:3100';
    await page.goto(`${uiBase}/control-center/roadmap`);
  // The Roadmap is available both at /control-center and /control-center/roadmap
  // Try the tab first; if not present, the dedicated route will still render the heading.
  const heading = page.getByRole('heading', { name: /Roadmap/i });
  await expect(heading).toBeVisible();
    const runButton = page.getByRole('button', { name: /Run Diagnostics/i });
    await expect(runButton).toBeVisible();

    // Basic assertion that at least one roadmap card hint is present
    // (manual or diag-mapped label rendered by the panel)
    const manualOrDiag = page.locator('text=/manual|diag-mapped/i');
    await expect(manualOrDiag.first()).toBeVisible();
  });
});
