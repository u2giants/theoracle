import { NextResponse } from 'next/server';
import { open, lstat } from 'node:fs/promises';
import { constants } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
const CHUNK = 1024 * 1024;
const MAX_ARCHIVE = 64 * CHUNK;
export async function deliverPublicSource(req: Request, directory = resolve(process.cwd(), '.source-offer')) {
  const url=new URL(req.url);
  if(req.method!=='GET'||url.search)return NextResponse.json({error:'Invalid source request'},{status:400});
  try {
    const directoryInfo=await lstat(directory);if(!directoryInfo.isDirectory()||directoryInfo.isSymbolicLink())throw Error('Invalid source directory');
    const bounded=async(path:string,limit:number)=>{const fd=await open(path,constants.O_RDONLY|constants.O_NOFOLLOW);try{const info=await fd.stat();if(!info.isFile()||info.size>limit)throw Error('Invalid source offer');const raw=await fd.readFile();if(raw.length>limit)throw Error('Invalid source offer');return raw;}finally{await fd.close();}};
    const manifest = JSON.parse((await bounded(resolve(directory, 'manifest.json'),CHUNK)).toString('utf8'));
    if(manifest.schema_version!==1||manifest.private_data_included!==false||!manifest.files||typeof manifest.files!=='object'||Array.isArray(manifest.files)||!/^[0-9a-f]{64}$/.test(manifest.source_hash))throw Error('Nonpublic source offer');
    if(Object.keys(manifest.files).some(p=>p.startsWith('/')||p.split('/').some((x:string)=>!x||x==='.'||x==='..')||!/^[0-9a-f]{64}$/.test(manifest.files[p]))||manifest.source_hash!==createHash('sha256').update(JSON.stringify(manifest.files)).digest('hex'))throw Error('Invalid source manifest');
    const path = resolve(directory, 'oracle-source.tar.gz');
    if ( !/^[0-9a-f]{64}$/.test(manifest.archive_sha256) || !/^[0-9a-f]{40}$/.test(manifest.revision)) throw new Error('Invalid source offer');
    const archive = await bounded(path,MAX_ARCHIVE);
    if (manifest.archive_sha256 !== createHash('sha256').update(archive).digest('hex')) throw new Error('Source integrity mismatch');
    const etag = `"${manifest.archive_sha256}"`;
    const headers = { 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'X-Oracle-Source-Revision': manifest.revision, ETag: etag, 'Accept-Ranges': 'bytes' };
    const match = req.headers.get('if-match');
    if (match && match !== etag) return NextResponse.json({ error: 'Source revision changed; restart download' }, { status: 412, headers });

    const range = req.headers.get('range');
    if (range) {
      const parsed = /^bytes=(0|[1-9][0-9]*)-(0|[1-9][0-9]*)$/.exec(range);
      const start = parsed ? Number(parsed[1]) : -1; const end = parsed ? Number(parsed[2]) : -1;
      if (!match || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end < start || end >= archive.length || end - start + 1 > CHUNK) return NextResponse.json({ error: 'A bounded range and exact source revision are required' }, { status: 416, headers: { ...headers, 'Content-Range': `bytes */${archive.length}` } });
      return new NextResponse(new Uint8Array(archive.subarray(start, end + 1)), { status: 206, headers: { ...headers, 'Content-Type': 'application/gzip', 'Content-Length': String(end - start + 1), 'Content-Range': `bytes ${start}-${end}/${archive.length}` } });
    }
    if (archive.length > 4 * CHUNK) return NextResponse.json({ error: 'Use bounded ranges with the exact source revision for this archive' }, { status: 413, headers });
    return new NextResponse(new Uint8Array(archive), { headers: { ...headers, 'Content-Type': 'application/gzip', 'Content-Disposition': 'attachment; filename="oracle-source.tar.gz"' } });
  } catch { return NextResponse.json({ error: 'Corresponding source is unavailable' }, { status: 503 }); }
}
