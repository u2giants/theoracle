import Link from 'next/link';
import { desc, eq, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { channels, channelParticipants, employees, messages } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

export const dynamic = 'force-dynamic';

export default async function AdminChannelsPage() {
  const db = getDirectDb();

  const rows = await db
    .select({
      id: channels.id,
      name: channels.name,
      isGroup: channels.isGroupChat,
      status: channels.status,
      createdAt: channels.createdAt,
      messageCount: sql<number>`COUNT(${messages.id})`.as('message_count'),
    })
    .from(channels)
    .leftJoin(messages, eq(messages.channelId, channels.id))
    .groupBy(channels.id)
    .orderBy(desc(channels.createdAt));

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Channels</h1>
        <p className="text-sm text-muted-foreground">
          Read-only view. Channel creation and participant management UI ships in Phase 5.
        </p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} channels</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Messages</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 pr-4">View</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="py-2 pr-4 font-medium">
                    {c.name ?? <em className="text-muted-foreground">(unnamed)</em>}
                  </td>
                  <td className="py-2 pr-4">{c.isGroup ? 'group' : 'direct'}</td>
                  <td className="py-2 pr-4">{c.status}</td>
                  <td className="py-2 pr-4">{c.messageCount}</td>
                  <td className="py-2 pr-4">
                    {formatNYDateTime(c.createdAt)}
                  </td>
                  <td className="py-2 pr-4">
                    <Link
                      href={`/admin/messages?channel=${c.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      transcripts →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
