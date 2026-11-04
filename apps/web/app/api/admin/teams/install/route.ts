// POST /api/admin/teams/install — Teams build-out phase 4.
// Installs the Oracle Teams app for every enabled @popcre.com user who does
// not have it yet, so the bot can open a 1:1 chat. Body {"dryRun": true}
// only counts. Admin session, or the brain shared token for server use.

import { NextResponse, type NextRequest } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';
import { installOracleForTenant } from '@/lib/teams-proactive-install';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

async function authorized(req: NextRequest): Promise<boolean> {
  const token = process.env.BRAIN_SHARED_TOKEN;
  if (token && req.headers.get('x-brain-token') === token) return true;
  try {
    await requireAdmin();
    return true;
  } catch {
    return false;
  }
}

export async function POST(req: NextRequest) {
  if (!(await authorized(req))) return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  const body = (await req.json().catch(() => ({}))) as { dryRun?: boolean };
  try {
    const result = await installOracleForTenant({ dryRun: body.dryRun === true });
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 502 });
  }
}
