// Trigger.dev v3 configuration.
// Default routing metadata lives in the protected local target profile.
// An explicit TRIGGER_PROJECT_REF keeps the existing staging override behaviour.
// See https://trigger.dev/docs/v3/config.

import { defineConfig } from '@trigger.dev/sdk/v3';
import { readPrivateTarget } from '../../dev/oracle2/private-target-profile.mjs';

export default defineConfig({
  project: process.env.TRIGGER_PROJECT_REF ?? readPrivateTarget('legacy_trigger_project'),
  runtime: 'node-24',
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
  // Oracle 2 tasks belong to separately credentialed preview deployments.
  // Never bundle them into the legacy project's credential-bearing runtime.
  ignorePatterns: ['**/oracle2-run.ts', '**/oracle2-project.ts', '**/oracle2-holistic.ts', '**/oracle2-operating-model.ts', '**/oracle2-native-invented.ts', '**/oracle2-native-invented-v2.ts'],
});
