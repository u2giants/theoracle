// POST /api/admin/brain/synthesize
//
// Admin-only endpoint to manually trigger brain synthesis for a given section.
// Dispatches the Trigger.dev 'brain-synthesis' task and returns immediately.
// The actual synthesis runs asynchronously.
//
// Request body: { sectionId: string, trigger?: 'admin' | 'new_claims' }

import { NextResponse, type NextRequest } from 'next/server';
import { z } from 'zod';
import { requireAdmin } from '@/lib/auth-guard';
import { triggerTask } from '@/lib/trigger';
import { getDirectDb } from '@oracle/db/client';
import { eq } from 'drizzle-orm';
import { brainSections } from '@oracle/db/schema';

export const dynamic = 'force-dynamic';

const BodySchema = z.object({
  sectionId: z.string().min(1),
  trigger: z.enum(['admin', 'new_claims']).optional().default('admin'),
});

export async function POST(req: NextRequest) {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await req.json());
  } catch (err) {
    return NextResponse.json({ error: 'bad_request', detail: String(err) }, { status: 400 });
  }

  // Verify the section exists.
  const db = getDirectDb();
  const [section] = await db
    .select({ id: brainSections.id, title: brainSections.title })
    .from(brainSections)
    .where(eq(brainSections.id, body.sectionId))
    .limit(1);

  if (!section) {
    return NextResponse.json(
      { error: 'not_found', detail: `Brain section "${body.sectionId}" does not exist.` },
      { status: 404 },
    );
  }

  const dispatched = await triggerTask('brain-synthesis', {
    sectionId: body.sectionId,
    trigger: body.trigger,
  });

  if (!dispatched) {
    // Don't report `triggered: true` when dispatch failed. brain-synthesis only
    // has a weekly sweep, so silently claiming success could leave the section
    // stale for days with no signal.
    return NextResponse.json(
      {
        error: 'dispatch_failed',
        sectionId: body.sectionId,
        title: section.title,
        detail:
          'Synthesis task could not be dispatched (check TRIGGER_SECRET_KEY). It will only be retried by the weekly sweep.',
      },
      { status: 502 },
    );
  }

  return NextResponse.json({
    ok: true,
    sectionId: body.sectionId,
    title: section.title,
    triggered: true,
    note: 'Synthesis task dispatched. Check admin/brain for results.',
  });
}
