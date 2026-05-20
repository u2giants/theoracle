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
] as const;

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const me = await requireAdmin();
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
            </nav>
          </div>
          <div className="flex items-center gap-3">
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
