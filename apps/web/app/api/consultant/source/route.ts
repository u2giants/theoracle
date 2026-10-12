import { NextResponse, type NextRequest } from 'next/server';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export async function GET(req: NextRequest) {
  const auth = await authorizePilotRequest(req.headers);
  if (!auth.ok) return NextResponse.json({ error: auth.error }, { status: auth.status });
  try {
    const directory = resolve(process.cwd(), '.source-offer');
    const manifest = JSON.parse(await readFile(resolve(directory, 'manifest.json'), 'utf8'));
    const archive = await readFile(resolve(directory, 'oracle-source.tar.gz'));
    if (manifest.archive_sha256 !== createHash('sha256').update(archive).digest('hex')) throw new Error('Source integrity mismatch');
    return new NextResponse(new Uint8Array(archive), { headers: {
      'Content-Type': 'application/gzip',
      'Content-Disposition': 'attachment; filename="oracle-source.tar.gz"',
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
      'X-Oracle-Source-Revision': manifest.revision,
    } });
  } catch { return NextResponse.json({ error: 'Corresponding source is unavailable' }, { status: 503 }); }
}
