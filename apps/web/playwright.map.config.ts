import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';
import { e2eEnv, WEB_DIR } from './tests/map/env';

// Company Map browser test (plan step 10): the brain API on the projected
// fixture map, the Next.js app, and a localhost stand-in for Supabase Auth.
const brainDir = resolve(WEB_DIR, '..', 'brain');
const authUrl = `http://localhost:${e2eEnv.authPort}`;

export default defineConfig({
  testDir: './tests',
  testMatch: 'map.spec.ts',
  timeout: 120_000,
  retries: 0,
  workers: 1,
  globalSetup: './tests/map/global-setup.ts',
  use: {
    baseURL: `http://localhost:${e2eEnv.webPort}`,
    headless: true,
    viewport: { width: 1400, height: 900 },
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: 'node tests/map/fake-supabase-auth.mjs',
      url: `${authUrl}/health`,
      reuseExistingServer: false,
      env: {
        MAP_E2E_AUTH_PORT: String(e2eEnv.authPort),
        MAP_E2E_ACCESS_TOKEN: e2eEnv.accessToken,
        MAP_E2E_AUTH_USER_ID: e2eEnv.authUserId,
      },
    },
    {
      command: `uv run uvicorn brain.main:app --host 127.0.0.1 --port ${e2eEnv.brainPort}`,
      cwd: brainDir,
      url: `http://127.0.0.1:${e2eEnv.brainPort}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        DATABASE_URL: e2eEnv.databaseUrl,
        FALKORDB_URL: e2eEnv.falkordbUrl,
        BRAIN_SHARED_TOKEN: e2eEnv.brainToken,
      },
    },
    {
      command: `pnpm exec next dev -p ${e2eEnv.webPort}`,
      url: `http://localhost:${e2eEnv.webPort}/denied`,
      reuseExistingServer: false,
      timeout: 240_000,
      env: {
        NEXT_PUBLIC_SUPABASE_URL: authUrl,
        NEXT_PUBLIC_SUPABASE_ANON_KEY: 'map-e2e-anon-key',
        DATABASE_URL: e2eEnv.databaseUrl,
        BRAIN_BASE_URL: `http://127.0.0.1:${e2eEnv.brainPort}`,
        BRAIN_SHARED_TOKEN: e2eEnv.brainToken,
        NEXT_TELEMETRY_DISABLED: '1',
      },
    },
  ],
});
