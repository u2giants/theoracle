import type { NextConfig } from 'next';
import { config as loadEnv } from 'dotenv';
import { resolve } from 'node:path';
import { execSync } from 'node:child_process';

// Load .env.local from the monorepo root so `pnpm --filter @oracle/web dev`
// picks up secrets without us having to duplicate the file into apps/web/.
// Next.js's built-in dotenv loader only checks the app's own directory.
loadEnv({ path: resolve(__dirname, '..', '..', '.env.local') });
loadEnv({ path: resolve(__dirname, '..', '..', '.env') });

// Capture git commit info at build time so the running version is visible in
// the admin header without any runtime git dependency.
function getGitInfo(): { sha: string; timestamp: string } {
  try {
    const sha = execSync('git log -1 --format=%H', { encoding: 'utf8' }).trim();
    const timestamp = execSync('git log -1 --format=%ct', { encoding: 'utf8' }).trim();
    return { sha, timestamp };
  } catch {
    return { sha: 'unknown', timestamp: '0' };
  }
}

const git = getGitInfo();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Transpile workspace packages — they ship as TypeScript source.
  transpilePackages: ['@oracle/shared', '@oracle/db', '@oracle/auth', '@oracle/ai'],
  // Next 16 moved this out of `experimental`.
  serverExternalPackages: ['postgres', 'pg'],
  // Build-time git info — baked into the bundle, available on server + client.
  env: {
    NEXT_PUBLIC_GIT_SHA: git.sha,
    NEXT_PUBLIC_GIT_TIMESTAMP: git.timestamp,
  },
};

export default nextConfig;
