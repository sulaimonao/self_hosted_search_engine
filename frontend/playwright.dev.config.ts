import { defineConfig } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_APP_URL || 'http://127.0.0.1:3100';

export default defineConfig({
  // Limit test discovery to the e2e tests folder to prevent pulling in
  // Vitest/unit tests or test helpers from `src`.
  testDir: './tests/e2e',
  timeout: 90_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  // No webServer here — your bash script starts API+Web.
});
