import { requestReplacementControl } from '../../../../../../../lib/replacement-protected-client';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const headers = Object.freeze({
  'Cache-Control': 'private, no-store, max-age=0',
  'Pragma': 'no-cache',
  'X-Content-Type-Options': 'nosniff',
});
const unavailable = () => Response.json({ error: 'Replacement control unavailable' }, { status: 503, headers });

/** Protected metadata only. Next rejects unexported methods. No fixture fallback,
 * durable store, role/identity selector, redirect or result-serving API. */
export async function POST(request: Request): Promise<Response> {
  try {
    const result = await requestReplacementControl(request);
    if (!result.available) return unavailable();
    const m = result.metadata;
    return Response.json({
      runId: m.runId,
      journeyRevision: m.journeyRevision,
      controlState: m.controlState,
      populationSha256: m.populationSha256,
      cancelRequested: m.cancelRequested,
      remoteStopProven: m.remoteStopProven,
      resultAvailable: m.resultAvailable,
    }, { status: 200, headers });
  } catch {
    return unavailable();
  }
}
