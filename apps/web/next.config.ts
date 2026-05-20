import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Transpile workspace packages — they ship as TypeScript source.
  transpilePackages: ['@oracle/shared', '@oracle/db', '@oracle/auth', '@oracle/ai'],
  experimental: {
    // postgres-js is a server-only native-ish dependency.
    serverComponentsExternalPackages: ['postgres', 'pg'],
  },
  eslint: {
    // We run lint via turbo; don't double-fail builds.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
