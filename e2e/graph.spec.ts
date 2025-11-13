// @ts-expect-error playwright test types are provided at runtime in e2e environment
import { expect, test } from '@playwright/test';

test.describe('Knowledge Graph', () => {
  test('loads and toggles between Pages and Sites views', async ({ page }: { page: any }) => {
    test.skip(process.env.CI === 'true', 'Graph UI e2e disabled on CI');

    const uiBase = process.env.UI_BASE_URL ?? 'http://127.0.0.1:3100';
    await page.goto(`${uiBase}/graph`);

    const heading = page.getByRole('heading', { name: /Knowledge Graph/i });
    await expect(heading).toBeVisible();

    const viewSelect = page.getByLabel(/View/i);
    await expect(viewSelect).toBeVisible();

    // Switch to Sites overview
    await viewSelect.selectOption({ label: /Sites \(overview\)/i });
    // Canvas should render even with empty data
    const canvases = page.locator('canvas');
    await expect(canvases.first()).toBeVisible();

    // Switch back to Pages and ensure Indexed only checkbox is visible
    await viewSelect.selectOption({ label: /Pages/i });
    const indexedCheckbox = page.getByRole('checkbox', { name: /Indexed only/i });
    await expect(indexedCheckbox).toBeVisible();
  });
});
