import { defineConfig } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_APP_URL || 'http://127.0.0.1:3100';
const apiURL = process.env.API_URL || 'http://127.0.0.1:5050/api/__meta';

export default defineConfig({
  timeout: 60_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  // Start API then Web; reuse if they’re already running.
  webServer: [
    {
      command: 'npm run dev:api',
      url: apiURL,
      timeout: 120_000,
      reuseExistingServer: true,
    },
    {
      command: 'npm run dev:web',
      url: baseURL,
      timeout: 120_000,
      reuseExistingServer: true,
    },
  ],
});
