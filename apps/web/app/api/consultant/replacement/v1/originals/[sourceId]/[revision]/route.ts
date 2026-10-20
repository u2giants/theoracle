// GET /api/consultant/replacement/v1/originals/[sourceId]/[revision]
// Original viewer capability: serves PNG page parts from the fixture store.
// Separate from executor serving; immutable hash-bound image only.
import { NextResponse, type NextRequest } from 'next/server';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ sourceId: string; revision: string }> },
) {
  const { sourceId, revision } = await context.params;
  const store = replacementFixtureStore();
  const stored = store.getSource(sourceId);
  if (!stored) {
    return NextResponse.json({ error: 'unknown source' }, { status: 404 });
  }
  const revisionNumber = Number.parseInt(revision, 10);
  if (!Number.isInteger(revisionNumber) || revisionNumber !== stored.source.revision) {
    return NextResponse.json({ error: 'unknown revision' }, { status: 404 });
  }
  const page = stored.pages[0];
  if (!page) {
    return NextResponse.json({ error: 'no page part' }, { status: 404 });
  }
  return new NextResponse(new Uint8Array(page.imagePng), {
    status: 200,
    headers: {
      'content-type': 'image/png',
      'content-length': String(page.byteCount),
      'x-image-sha256': page.imageSha256,
      'x-page-number': String(page.pageNumber),
      'x-original-sha256': stored.source.originalSha256,
      'cache-control': 'private, no-store',
    },
  });
}
