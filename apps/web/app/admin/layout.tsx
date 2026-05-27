import Link from 'next/link';
import { requireAdmin } from '@/lib/auth-guard';
import { LogoutButton } from '@/app/_components/logout-button';

export const dynamic = 'force-dynamic';

const TABS = [
  { href: '/admin', label: 'Employees' },
  { href: '/admin/channels', label: 'Channels' },
  { href: '/admin/messages', label: 'Messages' },
  { href: '/admin/documents', label: 'Documents' },
  { href: '/admin/claims', label: 'Claims' },
  { href: '/admin/gaps', label: 'Gaps' },
  { href: '/admin/contradictions', label: 'Contradictions' },
  { href: '/admin/brain', label: 'Brain' },
  { href: '/admin/ai', label: 'AI Observability' },
  { href: '/admin/taxonomy', label: 'Taxonomy' },
  { href: '/admin/settings', label: 'Settings' },
] as const;

// Chat-rooms link lives outside the admin tabs array because it navigates
// out of /admin entirely.
const CHAT_HREF = '/channels';

function buildVersion(): { sha: string; label: string } | null {
  const sha = process.env.NEXT_PUBLIC_GIT_SHA;
  const ts = parseInt(process.env.NEXT_PUBLIC_GIT_TIMESTAMP ?? '0', 10);
  if (!sha || sha === 'unknown' || !ts) return null;
  const label = new Date(ts * 1000).toLocaleString('en-US', {
    timeZone: 'America/New_York',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
  return { sha: sha.slice(0, 7), label };
}

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const me = await requireAdmin();
  const version = buildVersion();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <div className="container flex items-center justify-between py-4">
          <div className="flex items-center gap-6">
            <Link href="/admin" className="text-lg font-semibold">
              The Oracle · Admin
            </Link>
            <nav className="flex gap-3 text-sm">
              {TABS.map((t) => (
                <Link
                  key={t.href}
                  href={t.href}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {t.label}
                </Link>
              ))}
              <Link
                href={CHAT_HREF}
                className="font-medium text-foreground hover:text-foreground"
                title="Go to chat rooms"
              >
                ↗ Chat
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            {version && (
              <div className="text-right text-[11px] leading-tight text-muted-foreground/70 font-mono">
                <div>{version.sha}</div>
                <div>{version.label}</div>
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              {me.name} · {me.role}
            </div>
            <LogoutButton />
          </div>
        </div>
      </header>
      <main className="container py-8">{children}</main>
    </div>
  );
}
