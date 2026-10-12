import { NextResponse, type NextRequest } from 'next/server';
import { readFile, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
const CHUNK = 1024 * 1024;
const MAX_ARCHIVE = 64 * CHUNK;
export async function GET(req: NextRequest) {
  const auth = await authorizePilotRequest(req.headers);
  if (!auth.ok) return NextResponse.json({ error: auth.error }, { status: auth.status });
  try {
    const directory = resolve(process.cwd(), '.source-offer');
    const manifest = JSON.parse(await readFile(resolve(directory, 'manifest.json'), 'utf8'));
    const path = resolve(directory, 'oracle-source.tar.gz');
    const info = await stat(path);
    if (!info.isFile() || info.size > MAX_ARCHIVE || !/^[0-9a-f]{64}$/.test(manifest.archive_sha256) || !/^[0-9a-f]{40}$/.test(manifest.revision)) throw new Error('Invalid source offer');
    const archive = await readFile(path);
    if (manifest.archive_sha256 !== createHash('sha256').update(archive).digest('hex')) throw new Error('Source integrity mismatch');
    const etag = `"${manifest.archive_sha256}"`;
    const headers = { 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'X-Oracle-Source-Revision': manifest.revision, ETag: etag, 'Accept-Ranges': 'bytes' };
    const match = req.headers.get('if-match');
    if (match && match !== etag) return NextResponse.json({ error: 'Source revision changed; restart download' }, { status: 412, headers });
    if (req.nextUrl.searchParams.get('metadata') === '1') return NextResponse.json({ revision: manifest.revision, sha256: manifest.archive_sha256, bytes: archive.length, chunk_bytes: CHUNK }, { headers });
    const range = req.headers.get('range');
    if (range) {
      const parsed = /^bytes=(0|[1-9][0-9]*)-(0|[1-9][0-9]*)$/.exec(range);
      const start = parsed ? Number(parsed[1]) : -1; const end = parsed ? Number(parsed[2]) : -1;
      if (!match || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end < start || end >= archive.length || end - start + 1 > CHUNK) return NextResponse.json({ error: 'A bounded range and exact source revision are required' }, { status: 416, headers: { ...headers, 'Content-Range': `bytes */${archive.length}` } });
      return new NextResponse(new Uint8Array(archive.subarray(start, end + 1)), { status: 206, headers: { ...headers, 'Content-Type': 'application/gzip', 'Content-Length': String(end - start + 1), 'Content-Range': `bytes ${start}-${end}/${archive.length}` } });
    }
    if (archive.length > 4 * CHUNK) return NextResponse.json({ error: 'Use the authenticated source download control for this archive' }, { status: 413, headers });
    return new NextResponse(new Uint8Array(archive), { headers: { ...headers, 'Content-Type': 'application/gzip', 'Content-Disposition': 'attachment; filename="oracle-source.tar.gz"' } });
  } catch { return NextResponse.json({ error: 'Corresponding source is unavailable' }, { status: 503 }); }
}
