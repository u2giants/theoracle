import Link from 'next/link';
import { eq, sql, desc } from 'drizzle-orm';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { channels, channelParticipants, messages } from '@oracle/db/schema';
import { cn } from '@/lib/utils';
import { LogoutButton } from '@/app/_components/logout-button';
import { formatNYDateTime } from '@/lib/time';

export const dynamic = 'force-dynamic';

export default async function ChannelsLayout({ children }: { children: React.ReactNode }) {
  const me = await requireEmployee();
  const db = getDirectDb();

  // List channels this employee belongs to, with last message timestamp.
  const myChannels = await db
    .select({
      id: channels.id,
      name: channels.name,
      isGroup: channels.isGroupChat,
      status: channels.status,
      lastMessageAt: sql<Date | null>`MAX(${messages.createdAt})`.as('last_message_at'),
    })
    .from(channels)
    .innerJoin(channelParticipants, eq(channelParticipants.channelId, channels.id))
    .leftJoin(messages, eq(messages.channelId, channels.id))
    .where(eq(channelParticipants.employeeId, me.id))
    .groupBy(channels.id)
    .orderBy(desc(sql`MAX(${messages.createdAt})`));

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="shrink-0 border-b">
        <div className="flex items-center justify-between px-6 py-3">
          <Link href="/channels" className="text-base font-semibold">
            The Oracle
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/claims" className="text-sm text-muted-foreground hover:text-foreground">
              Claims
            </Link>
            {me.isAdmin ? (
              <Link href="/admin" className="text-sm text-muted-foreground hover:text-foreground">
                ↗ Admin
              </Link>
            ) : null}
            <span className="text-xs text-muted-foreground">{me.name}</span>
            <LogoutButton />
          </div>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
      <aside className="flex w-72 shrink-0 flex-col overflow-y-auto border-r bg-muted/30 p-4">
        <div className="mb-4">
          <Link href="/channels" className="font-semibold">
            Channels
          </Link>
        </div>
        <nav className="space-y-1 text-sm">
          {myChannels.length === 0 ? (
            <p className="text-muted-foreground">
              You aren&apos;t a member of any channels yet. Ask an admin.
            </p>
          ) : null}
          {myChannels.map((c) => (
            <Link
              key={c.id}
              href={`/channels/${c.id}`}
              className={cn(
                'block rounded-md px-3 py-2 hover:bg-accent',
                c.status !== 'active' && 'opacity-50',
              )}
            >
              <div className="font-medium">
                {c.name ?? (c.isGroup ? 'Group chat' : 'Direct message')}
              </div>
              <div className="text-xs text-muted-foreground">
                {c.isGroup ? 'group' : 'direct'} ·{' '}
                {c.lastMessageAt
                  ? formatNYDateTime(c.lastMessageAt)
                  : 'no messages yet'}
              </div>
            </Link>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
