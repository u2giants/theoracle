// Channel detail — chat UI for both 1:1 and group rooms.
// Realtime subscription happens client-side via Supabase Realtime (RLS-gated
// by the participant policy). Server-side renders initial message history.

import { notFound } from 'next/navigation';
import { and, asc, desc, eq } from 'drizzle-orm';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import {
  channels,
  channelParticipants,
  employees,
  messages,
} from '@oracle/db/schema';
import { ChannelChat } from './_components/channel-chat';

export const dynamic = 'force-dynamic';

const INITIAL_MESSAGE_LIMIT = 50;

export default async function ChannelPage({
  params,
}: {
  params: Promise<{ channelId: string }>;
}) {
  const { channelId } = await params;
  const me = await requireEmployee();
  const db = getDirectDb();

  // Confirm membership (defense in depth — RLS would also block, but this is
  // a server component using the service role).
  const membership = await db
    .select()
    .from(channelParticipants)
    .where(
      and(
        eq(channelParticipants.channelId, channelId),
        eq(channelParticipants.employeeId, me.id),
      ),
    )
    .limit(1);

  if (membership.length === 0) notFound();

  const channelRows = await db
    .select()
    .from(channels)
    .where(eq(channels.id, channelId))
    .limit(1);
  const channel = channelRows[0];
  if (!channel) notFound();

  // Recent messages (chronological for display).
  const recent = await db
    .select({
      id: messages.id,
      channelId: messages.channelId,
      employeeId: messages.employeeId,
      role: messages.role,
      content: messages.content,
      createdAt: messages.createdAt,
      authorName: employees.name,
    })
    .from(messages)
    .leftJoin(employees, eq(messages.employeeId, employees.id))
    .where(eq(messages.channelId, channelId))
    .orderBy(desc(messages.createdAt))
    .limit(INITIAL_MESSAGE_LIMIT);

  const inOrder = recent.reverse();

  // Participant list (for presence display)
  const participants = await db
    .select({
      id: employees.id,
      name: employees.name,
      role: employees.role,
    })
    .from(channelParticipants)
    .innerJoin(employees, eq(channelParticipants.employeeId, employees.id))
    .where(eq(channelParticipants.channelId, channelId))
    .orderBy(asc(employees.name));

  return (
    <ChannelChat
      channel={channel}
      me={me}
      initialMessages={inOrder}
      participants={participants}
    />
  );
}
