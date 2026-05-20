import type { NextConfig } from 'next';
import { config as loadEnv } from 'dotenv';
import { resolve } from 'node:path';

// Load .env.local from the monorepo root so `pnpm --filter @oracle/web dev`
// picks up secrets without us having to duplicate the file into apps/web/.
// Next.js's built-in dotenv loader only checks the app's own directory.
loadEnv({ path: resolve(__dirname, '..', '..', '.env.local') });
loadEnv({ path: resolve(__dirname, '..', '..', '.env') });

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Transpile workspace packages — they ship as TypeScript source.
  transpilePackages: ['@oracle/shared', '@oracle/db', '@oracle/auth', '@oracle/ai'],
  // Next 16 moved this out of `experimental`.
  serverExternalPackages: ['postgres', 'pg'],
};

export default nextConfig;
