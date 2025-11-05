import { defineConfig } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_APP_URL || 'http://127.0.0.1:3100';

export default defineConfig({
  timeout: 90_000,
  use: { baseURL, trace: 'retain-on-failure' },

  // Start API (from repo root) then WEB (from frontend)
  webServer: [
    {
      // run backend from the repo root
      command: 'npm run dev:api',
      url: 'http://127.0.0.1:5050/api/__meta',
      timeout: 120_000,
      reuseExistingServer: true,
      cwd: '..',
      env: { LANGSMITH_ENABLED: '0' },
    },
    {
      // run next dev using root script so envs match `dev:desktop`
      command: 'npm run dev:web',
      url: baseURL,
      timeout: 120_000,
      reuseExistingServer: true,
      cwd: '..',
    },
  ],
});
