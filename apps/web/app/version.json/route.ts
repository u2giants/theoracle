import { NextResponse } from 'next/server';

// Known version path the deploy check reads after Vercel deploys
// (scripts/verify-live-version.sh compares git_sha with the merged commit).
// NEXT_PUBLIC_GIT_SHA is baked at build time by next.config.ts (same value the
// admin header shows), so this response describes the build that serves it.
export const dynamic = 'force-static';

export function GET() {
  return NextResponse.json(
    { git_sha: process.env.NEXT_PUBLIC_GIT_SHA ?? 'unknown' },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
