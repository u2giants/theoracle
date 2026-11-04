// POST /api/admin/teams/install — Teams build-out phase 4.
// Installs the Oracle Teams app for every enabled @popcre.com user who does
// not have it yet, so the bot can open a 1:1 chat. Body {"dryRun": true}
// only counts. Admin session, or the brain shared token for server use.

import { NextResponse, type NextRequest } from 'next/server';
import { getCurrentEmployee } from '@/lib/auth-guard';
import { installOracleForTenant, TeamsInstallConfigurationError } from '@/lib/teams-proactive-install';

import { isBrainToken } from '@/lib/brain-service';
import { GraphNotConfiguredError } from '@/lib/microsoft-graph';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

async function authorized(req: NextRequest): Promise<boolean> {
  if (isBrainToken(req.headers.get('x-brain-token'))) return true;
  return Boolean((await getCurrentEmployee())?.isAdmin);
}

export async function POST(req: NextRequest) {
  try {
    if (!(await authorized(req))) return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  } catch {
    return NextResponse.json({ error: 'Authorization service failed' }, { status: 500 });
  }
  const body: unknown = await req.json().catch(() => null);
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return NextResponse.json({ error: 'Expected a JSON object' }, { status: 400 });
  }
  const { dryRun, cursor } = body as { dryRun?: unknown; cursor?: unknown };
  if ((dryRun !== undefined && typeof dryRun !== 'boolean') ||
      (cursor !== undefined && typeof cursor !== 'string')) {
    return NextResponse.json({ error: 'Invalid dryRun or cursor' }, { status: 400 });
  }
  try {
    const result = await installOracleForTenant({ dryRun: dryRun !== false, cursor: cursor as string | undefined });
    return NextResponse.json(result);
  } catch (err) {
    const status = err instanceof TeamsInstallConfigurationError || err instanceof GraphNotConfiguredError ? 503 : 502;
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status });
  }
}
