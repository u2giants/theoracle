// GET /api/consultant/runs/[id] — retrieve a run by ID.
import { NextResponse, type NextRequest } from 'next/server';
import { getRun } from '@/lib/oracle2-client';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const run = getRun(id);
  if (!run) {
    return NextResponse.json({ error: 'run not found' }, { status: 404 });
  }
  return NextResponse.json(run);
}
