// Trigger.dev v3 configuration.
// The project ref is a public identifier, not a secret — committed here so
// `pnpm --filter @oracle/workers run deploy` works against a fresh checkout
// without env juggling. TRIGGER_PROJECT_REF can still override (e.g. for a
// future staging project).
// See https://trigger.dev/docs/v3/config.

import { defineConfig } from '@trigger.dev/sdk/v3';

export default defineConfig({
  project: process.env.TRIGGER_PROJECT_REF ?? 'proj_wgpzsvhmsopqhvwqaycn',
  runtime: 'node',
  logLevel: 'info',
  maxDuration: 60 * 10, // 10 minutes per run
  retries: {
    enabledInDev: false,
    default: {
      maxAttempts: 3,
      minTimeoutInMs: 5_000,
      maxTimeoutInMs: 60_000,
      factor: 2,
      randomize: true,
    },
  },
  dirs: ['./src/trigger'],
});
