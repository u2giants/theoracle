import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/oracle2',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.ORACLE2_PREVIEW_URL ?? 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'oracle2-pilot',
      testMatch: '**/*.spec.ts',
    },
  ],
});
