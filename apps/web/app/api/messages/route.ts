// POST /api/messages — server-side message insert.
//
// Writes go through this route instead of the browser Supabase client so that:
//   * The insert uses the service-role connection (DIRECT_URL) which bypasses
//     the browser-client auth / RLS layer entirely.
//   * requireEmployee() validates the session server-side — the same path that
//     already works for every other server component.
//
// The browser realtime subscription still handles delivery of the inserted row.

import { NextResponse, type NextRequest } from 'next/server';
import { eq, and } from 'drizzle-orm';
import { z } from 'zod';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { channels, channelParticipants, messages } from '@oracle/db/schema';

export const dynamic = 'force-dynamic';

const BodySchema = z.object({
  channelId: z.uuid(),
  content: z.string().min(1).max(10_000),
});

export async function POST(request: NextRequest) {
  // 1. Authenticate — same guard used by every server component.
  let me;
  try {
    me = await requireEmployee();
  } catch {
    // requireEmployee redirects via next/navigation; if called from fetch()
    // it throws instead. Return a clean 401.
    return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 });
  }

  // 2. Parse + validate body.
  let body: { channelId: string; content: string };
  try {
    body = BodySchema.parse(await request.json());
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const db = getDirectDb();

  // 3. Confirm the caller is a participant of this channel.
  const membership = await db
    .select()
    .from(channelParticipants)
    .where(
      and(
        eq(channelParticipants.channelId, body.channelId),
        eq(channelParticipants.employeeId, me.id),
      ),
    )
    .limit(1);

  if (membership.length === 0) {
    return NextResponse.json({ error: 'Not a channel participant' }, { status: 403 });
  }

  // 4. Confirm the channel is active.
  const channelRows = await db
    .select({ status: channels.status })
    .from(channels)
    .where(eq(channels.id, body.channelId))
    .limit(1);

  if (!channelRows[0] || channelRows[0].status !== 'active') {
    return NextResponse.json({ error: 'Channel not found or not active' }, { status: 404 });
  }

  // 5. Insert the message.
  const inserted = await db
    .insert(messages)
    .values({
      channelId: body.channelId,
      employeeId: me.id,
      role: 'user',
      content: body.content,
    })
    .returning();

  const msg = inserted[0];
  if (!msg) {
    return NextResponse.json({ error: 'Insert failed' }, { status: 500 });
  }

  return NextResponse.json(
    {
      id: msg.id,
      channelId: msg.channelId,
      employeeId: msg.employeeId,
      role: msg.role,
      content: msg.content,
      createdAt: msg.createdAt,
    },
    { status: 201 },
  );
}
