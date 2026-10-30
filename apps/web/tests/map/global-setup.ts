// Seeds the projected fixture map for the Company Map browser test by running
// apps/brain/tests/map_seed.py against the throwaway database in
// BRAIN_E2E_DATABASE_URL, and records the ids the spec needs.
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { e2eEnv, SEED_FILE, WEB_DIR } from './env';

export default function globalSetup(): void {
  const brainDir = resolve(WEB_DIR, '..', 'brain');
  const out = execFileSync('uv', ['run', 'python', 'tests/map_seed.py'], {
    cwd: brainDir,
    env: {
      ...process.env,
      DATABASE_URL: e2eEnv.databaseUrl,
      FALKORDB_URL: e2eEnv.falkordbUrl,
      MAP_SEED_ALLOW: '1',
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  const line = out.trim().split('\n').pop() ?? '{}';
  JSON.parse(line);
  mkdirSync(resolve(SEED_FILE, '..'), { recursive: true });
  writeFileSync(SEED_FILE, line);
}
