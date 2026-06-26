// GET  /api/admin/settings          — read all settings rows
// POST /api/admin/settings          — upsert a single setting by key
//
// Both endpoints require admin.

import { NextResponse, type NextRequest } from 'next/server';
import { eq } from 'drizzle-orm';
import { z } from 'zod';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { normalizeSettingValue } from '@oracle/ai';

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
