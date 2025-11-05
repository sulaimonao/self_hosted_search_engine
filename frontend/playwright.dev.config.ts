import { defineConfig } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_APP_URL || 'http://127.0.0.1:3100';

export default defineConfig({
  timeout: 90_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  // No webServer here — your bash script starts API+Web.
});
