import { and, desc, eq, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { channels, messages } from '@oracle/db/schema';
import { AdminImportForm } from './import-form';

export const dynamic = 'force-dynamic';

export default async function AdminImportPage() {
  const db = getDirectDb();
  const channelRows = await db
    .select({
      id: channels.id,
      name: channels.name,
      createdAt: channels.createdAt,
      messageCount: sql<number>`COUNT(${messages.id})`.as('message_count'),
    })
    .from(channels)
    .leftJoin(messages, eq(messages.channelId, channels.id))
    .where(and(eq(channels.status, 'active'), eq(channels.isGroupChat, true)))
    .groupBy(channels.id)
    .orderBy(desc(channels.createdAt))
    .limit(50);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Import</h1>
        <p className="text-sm text-muted-foreground">
          Queue raw operational information as traceable source messages for the extraction pipeline.
        </p>
      </header>

      <AdminImportForm
        channels={channelRows.map((channel) => ({
          id: channel.id,
          name: channel.name ?? '(unnamed channel)',
          messageCount: Number(channel.messageCount),
        }))}
      />
    </div>
  );
}
