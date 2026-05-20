import { and, desc, eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { channels, employees, messages } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 100;

export default async function AdminMessagesPage({
  searchParams,
}: {
  searchParams: Promise<{ channel?: string }>;
}) {
  const { channel } = await searchParams;
  const db = getDirectDb();

  const channelRows = channel
    ? await db.select().from(channels).where(eq(channels.id, channel)).limit(1)
    : [];
  const targetChannel = channelRows[0] ?? null;

  const rows = await db
    .select({
      id: messages.id,
      content: messages.content,
      role: messages.role,
      createdAt: messages.createdAt,
      channelId: messages.channelId,
      authorName: employees.name,
      extractionStatus: messages.extractionStatus,
    })
    .from(messages)
    .leftJoin(employees, eq(messages.employeeId, employees.id))
    .where(channel ? eq(messages.channelId, channel) : undefined)
    .orderBy(desc(messages.createdAt))
    .limit(PAGE_SIZE);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">
          Messages
          {targetChannel
            ? ` — ${targetChannel.name ?? '(unnamed channel)'}`
            : ' — all channels'}
        </h1>
        <p className="text-sm text-muted-foreground">
          Read-only transcripts. Most recent {PAGE_SIZE}. Pagination ships in Phase 5.
        </p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} messages</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {rows.map((m) => (
              <div key={m.id} className="rounded-md border bg-card p-3">
                <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium">{m.authorName ?? m.role}</span>
                  <span>·</span>
                  <span>{new Date(m.createdAt).toLocaleString()}</span>
                  <span>·</span>
                  <span>{m.role}</span>
                  <span>·</span>
                  <span>{m.extractionStatus}</span>
                </div>
                <div className="whitespace-pre-wrap text-sm">{m.content}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
