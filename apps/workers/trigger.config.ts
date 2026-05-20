// Trigger.dev v3 configuration — Phase 4 scaffold.
// Populate TRIGGER_PROJECT_REF in Vercel env once the Trigger.dev project is
// created. See https://trigger.dev/docs/v3/config.

import { defineConfig } from '@trigger.dev/sdk/v3';

export default defineConfig({
  project: process.env.TRIGGER_PROJECT_REF ?? 'TODO_set_trigger_project_ref',
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
