// R10.5 — Sub-nav for /admin/taxonomy.

import Link from 'next/link';

const TABS = [
  { href: '/admin/taxonomy', label: 'Top-level domains' },
  { href: '/admin/taxonomy/proposals', label: 'Proposals' },
  { href: '/admin/taxonomy/entities', label: 'Entity registry' },
  { href: '/admin/taxonomy/entity-proposals', label: 'Entity proposals' },
  { href: '/admin/taxonomy/change-log', label: 'Change log' },
] as const;

export default function TaxonomyLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <nav className="flex flex-wrap gap-2 border-b pb-3 text-sm">
        {TABS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="rounded px-3 py-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {t.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
