// Shared settings for the Company Map browser test (plan step 10).
// BRAIN_E2E_DATABASE_URL must point at a throwaway database: the seed
// truncates cmap.* there. FalkorDB likewise gets its own instance.
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// apps/web, resolved without __dirname (this package is ESM).
export const WEB_DIR = fileURLToPath(new URL('../../', import.meta.url));

export const e2eEnv = {
  databaseUrl:
    process.env.BRAIN_E2E_DATABASE_URL ?? 'postgresql://oracle:oracle@127.0.0.1:56789/brain_e2e',
  falkordbUrl: process.env.BRAIN_E2E_FALKORDB_URL ?? 'redis://127.0.0.1:56792',
  brainPort: Number(process.env.MAP_E2E_BRAIN_PORT ?? 8799),
  webPort: Number(process.env.MAP_E2E_WEB_PORT ?? 3100),
  authPort: Number(process.env.MAP_E2E_AUTH_PORT ?? 54399),
  brainToken: 'map-e2e-brain-token',
  accessToken: 'map-e2e-access-token',
  authUserId: '00000000-0000-4000-8000-0000000000e2',
};

export const SEED_FILE = resolve(WEB_DIR, 'test-results', 'map-seed.json');
