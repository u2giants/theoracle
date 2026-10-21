// Original viewer: separate current source-read capability showing PNG page
// parts from the fixture store. Not an executor raw grant.

export const dynamic = 'force-dynamic';

export default async function OriginalViewerPage({
  params,
}: {
  params: Promise<{ sourceId: string; revision: string }>;
}) {
  const { sourceId, revision } = await params;
  const src = `/api/consultant/replacement/v1/originals/${encodeURIComponent(sourceId)}/${encodeURIComponent(revision)}`;
  return (
    <div data-testid="original-viewer" className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Original viewer</h1>
      <p data-testid="viewer-source" className="text-sm text-gray-600">
        Source {sourceId} revision {revision}
      </p>
      {/* eslint-disable-next-line @next/next/no-img-element -- hash-bound fixture PNG served from our own API */}
      <img
        data-testid="original-page-image"
        src={src}
        alt={`Original page for source ${sourceId}`}
        className="rounded border"
        width={480}
        height={480}
      />
      <p data-testid="viewer-note" className="text-xs text-gray-500">
        Fixture PNG page part. Synthetic/invented only; not a real company original.
      </p>
    </div>
  );
}
