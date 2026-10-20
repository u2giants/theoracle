// POST /api/consultant/replacement/v1/sources
// Multipart/binary original upload for the offline replacement journey.
// Synthetic fixture only. Unknown body fields fail closed. actor/workspace are
// server-derived; caller identities in the body are ignored.
import { NextResponse, type NextRequest } from 'next/server';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

const PERMITTED_MEDIA = new Set([
  'application/pdf',
  'text/plain',
  'image/png',
  'application/octet-stream',
]);

export async function POST(req: NextRequest) {
  try {
    const store = replacementFixtureStore();
    const contentType = req.headers.get('content-type') ?? '';
    let bytes: Buffer;
    let filename = 'original.bin';
    let mediaType = 'application/octet-stream';
    let staleSeeded: { label: string; modelId: string; contentHash: string } | null = null;

    if (contentType.includes('multipart/form-data')) {
      const form = await req.formData();
      const file = form.get('file');
      if (!(file instanceof File)) {
        return NextResponse.json({ error: 'file is required' }, { status: 400 });
      }
      filename = file.name || filename;
      mediaType = file.type || mediaType;
      bytes = Buffer.from(await file.arrayBuffer());
      const staleLabel = form.get('staleSeededLabel');
      const staleModelId = form.get('staleSeededModelId');
      const staleHash = form.get('staleSeededContentHash');
      if (typeof staleLabel === 'string' && staleLabel && typeof staleModelId === 'string' && typeof staleHash === 'string') {
        staleSeeded = { label: staleLabel, modelId: staleModelId, contentHash: staleHash };
      }
      // Strict unknown-field refusal for non-file parts.
      for (const key of form.keys()) {
        if (
          key !== 'file' &&
          key !== 'staleSeededLabel' &&
          key !== 'staleSeededModelId' &&
          key !== 'staleSeededContentHash'
        ) {
          return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
        }
      }
    } else if (contentType.includes('application/json')) {
      const body = (await req.json()) as Record<string, unknown>;
      const allowed = new Set(['filename', 'contentType', 'bytesBase64', 'staleSeeded']);
      for (const key of Object.keys(body)) {
        if (!allowed.has(key)) {
          return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
        }
      }
      const bytesBase64 = body.bytesBase64;
      if (typeof bytesBase64 !== 'string' || !bytesBase64) {
        return NextResponse.json({ error: 'bytesBase64 is required' }, { status: 400 });
      }
      bytes = Buffer.from(bytesBase64, 'base64');
      if (typeof body.filename === 'string') filename = body.filename;
      if (typeof body.contentType === 'string') mediaType = body.contentType;
      const stale = body.staleSeeded as
        | { label?: string; modelId?: string; contentHash?: string }
        | undefined;
      if (stale && typeof stale.label === 'string' && typeof stale.modelId === 'string' && typeof stale.contentHash === 'string') {
        staleSeeded = { label: stale.label, modelId: stale.modelId, contentHash: stale.contentHash };
      }
    } else {
      bytes = Buffer.from(await req.arrayBuffer());
    }

    if (!PERMITTED_MEDIA.has(mediaType)) {
      return NextResponse.json({ error: 'unsupported media type' }, { status: 415 });
    }
    if (bytes.length < 1 || bytes.length > 25 * 1024 * 1024) {
      return NextResponse.json({ error: 'original byte bound' }, { status: 400 });
    }

    // Workspace is server-owned fixture workspace; body identities ignored.
    const workspaceId = '00000000-0000-4000-8000-0000000000f1';
    const stored = store.registerSource({
      workspaceId,
      filename,
      contentType: mediaType,
      bytes,
      staleSeeded,
    });
    return NextResponse.json({
      sourceId: stored.source.sourceId,
      revision: stored.source.revision,
      originalSha256: stored.source.originalSha256,
      readingSha256: stored.source.readingSha256,
      parserId: stored.source.parserId,
      pageCount: stored.pages.length,
      hasStaleSeeded: Boolean(staleSeeded),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'upload failed';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
