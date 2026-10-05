// GET /api/consultant/runs/[id] — retrieve a run by ID (session required).
import { NextResponse, type NextRequest } from 'next/server';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import { getRun, pilotWorkspaceId } from '@/lib/oracle2-store';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const auth = authorizePilotRequest(req.headers);
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }
  const { id } = await params;
  const run = await getRun(id, pilotWorkspaceId(), auth.actorId);
  if (!run) {
    return NextResponse.json({ error: 'run not found' }, { status: 404 });
  }
  return NextResponse.json(run);
}
