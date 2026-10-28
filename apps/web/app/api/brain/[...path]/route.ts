// Proxy to the brain service (plan step 2). Every /map page calls the brain
// through this route so the shared token stays server-side; the request is
// forwarded with x-brain-token and the logged-in Supabase user id.

import { NextResponse, type NextRequest } from 'next/server';
import { getCurrentEmployee } from '@/lib/auth-guard';
import { getServerSupabase } from '@/lib/supabase/server';

export const dynamic = 'force-dynamic';
// Allow time for large uploads to forward through.
export const maxDuration = 60;

type RouteContext = { params: Promise<{ path: string[] }> };

function brainConfig(): { base: string; token: string } {
  const base = process.env.BRAIN_BASE_URL;
  const token = process.env.BRAIN_SHARED_TOKEN;
  if (!base || !token) {
    throw new Error('BRAIN_BASE_URL and BRAIN_SHARED_TOKEN must be set');
  }
  return { base: base.replace(/\/+$/, ''), token };
}

async function handle(req: NextRequest, path: string[]): Promise<NextResponse> {
  let me = null;
  try {
    me = await getCurrentEmployee();
  } catch {
    me = null;
  }
  if (!me) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getUser();
  const authUserId = data.user?.id;
  if (!authUserId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let config: { base: string; token: string };
  try {
    config = brainConfig();
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'brain is not configured' },
      { status: 500 },
    );
  }

  const suffix = path.map(encodeURIComponent).join('/');
  const target = `${config.base}/${suffix}${new URL(req.url).search}`;

  const headers = new Headers();
  headers.set('x-brain-token', config.token);
  headers.set('x-user-id', authUserId);
  const contentType = req.headers.get('content-type');
  if (contentType) {
    headers.set('content-type', contentType);
  }

  const init: RequestInit & { duplex?: 'half' } = {
    method: req.method,
    headers,
    redirect: 'manual',
  };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = req.body;
    init.duplex = 'half';
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return NextResponse.json({ error: 'brain unreachable' }, { status: 502 });
  }

  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get('content-type');
  if (upstreamType) {
    responseHeaders.set('content-type', upstreamType);
  }
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(req: NextRequest, ctx: RouteContext) {
  const { path } = await ctx.params;
  return handle(req, path ?? []);
}

export async function POST(req: NextRequest, ctx: RouteContext) {
  const { path } = await ctx.params;
  return handle(req, path ?? []);
}

export async function DELETE(req: NextRequest, ctx: RouteContext) {
  const { path } = await ctx.params;
  return handle(req, path ?? []);
}
