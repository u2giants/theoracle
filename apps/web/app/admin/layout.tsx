import Link from 'next/link';
import { requireAdmin } from '@/lib/auth-guard';
import { LogoutButton } from '@/app/_components/logout-button';
import { AdminNav } from './_components/admin-nav';
import { ModelAttemptAlertBanner } from './_components/model-attempt-alert-banner';
import { formatNYDateTime } from '@/lib/time';

export const dynamic = 'force-dynamic';

function buildVersion(): { sha: string; label: string } | null {
  const sha = process.env.NEXT_PUBLIC_GIT_SHA;
  const ts = parseInt(process.env.NEXT_PUBLIC_GIT_TIMESTAMP ?? '0', 10);
  if (!sha || sha === 'unknown' || !ts) return null;
  const label = formatNYDateTime(ts * 1000);
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
            <Link href="/admin" className="text-lg font-semibold whitespace-nowrap">
              The Oracle · Admin
            </Link>
            <AdminNav />
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
      <main className="container py-8">
        <ModelAttemptAlertBanner />
        {children}
      </main>
    </div>
  );
}
