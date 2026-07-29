// GET  /api/admin/settings          — read all settings rows
// POST /api/admin/settings          — upsert a single setting by key
//
// Both endpoints require admin.

import { NextResponse, type NextRequest } from 'next/server';
import { inArray } from 'drizzle-orm';
import { z } from 'zod';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import {
  normalizeSettingValue,
  providerSupportsTrackedBatch,
  resolveModelRoute,
} from '@oracle/ai';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const db = getDirectDb();
  const rows = await db.select().from(settings).orderBy(settings.key);
  return NextResponse.json({ settings: rows });
}

const UpsertSchema = z.object({
  key: z.string().min(1).max(100),
  value: z.unknown(),
  description: z.string().optional(),
});

export async function POST(req: NextRequest) {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  let body: z.infer<typeof UpsertSchema>;
  try {
    body = UpsertSchema.parse(await req.json());
  } catch (err) {
    return NextResponse.json(
      { error: 'Invalid request body', detail: String(err) },
      { status: 400 },
    );
  }

  const db = getDirectDb();
  // Idempotency / anti-double-encode guard (Bug 4): never persist an
  // already-JSON-encoded value into the jsonb column.
  const value = normalizeSettingValue(body.value);

  if (
    body.key === 'extraction_dispatch_mode' ||
    body.key === 'default_extraction_route'
  ) {
    const compatibilityRows = await db
      .select({ key: settings.key, value: settings.value })
      .from(settings)
      .where(
        inArray(settings.key, [
          'extraction_dispatch_mode',
          'default_extraction_route',
        ]),
      );
    const current = new Map(compatibilityRows.map((row) => [row.key, row.value]));
    const proposedMode =
      body.key === 'extraction_dispatch_mode'
        ? value
        : current.get('extraction_dispatch_mode');
    const proposedRoute =
      body.key === 'default_extraction_route'
        ? value
        : current.get('default_extraction_route');

    if (proposedMode === 'batch') {
      if (typeof proposedRoute !== 'string' || !proposedRoute) {
        return NextResponse.json(
          {
            error: 'Batch mode requires a configured extraction model.',
            detail: 'Choose an Anthropic, OpenAI, or Vertex extraction model first.',
          },
          { status: 409 },
        );
      }
      let provider;
      try {
        const resolved = resolveModelRoute(proposedRoute, 'extraction');
        if (!resolved) throw new Error('unresolved extraction route');
        provider = resolved.provider;
      } catch {
        return NextResponse.json(
          {
            error: 'The extraction model could not be resolved.',
            detail: 'Choose a valid extraction model before enabling Batch mode.',
          },
          { status: 409 },
        );
      }
      if (!providerSupportsTrackedBatch(provider)) {
        return NextResponse.json(
          {
            error: `${provider} does not have a tracked Batch path in Oracle.`,
            detail:
              'Keep Sync mode, or choose an Anthropic, OpenAI, or Vertex extraction model.',
          },
          { status: 409 },
        );
      }
    }
  }

  const [row] = await db
    .insert(settings)
    .values({
      key: body.key,
      value,
      ...(body.description !== undefined ? { description: body.description } : {}),
    })
    .onConflictDoUpdate({
      target: settings.key,
      set: {
        value,
        updatedAt: new Date(),
        ...(body.description !== undefined
          ? { description: body.description }
          : {}),
      },
    })
    .returning();

  return NextResponse.json({ setting: row }, { status: 200 });
}
