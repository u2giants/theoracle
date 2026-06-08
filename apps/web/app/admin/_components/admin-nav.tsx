'use client';

// Grouped admin nav with active-page highlighting.
//
// Items are organized into four logical groups (People → Activity →
// Knowledge → Operations), separated by thin dividers. The flat list was
// just-add-newest order which had become a wall of unrelated links.
//
// Active state is detected via usePathname so we need this to be a client
// component. The auth guard still runs server-side in the layout wrapper.

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

interface NavItem {
  href: string;
  label: string;
}
interface NavGroup {
  label: string;
  items: NavItem[];
}

// Order within each group is the order admins traverse them, not alphabetical.
const GROUPS: NavGroup[] = [
  {
    label: 'People',
    items: [
      { href: '/admin/employees', label: 'Employees' },
      { href: '/admin/departments', label: 'Departments' },
      { href: '/admin/channels', label: 'Channels' },
    ],
  },
  {
    label: 'Activity',
    // Messages + Documents — the raw inputs the Oracle reads from.
    items: [
      { href: '/admin/import', label: 'Import' },
      { href: '/admin/messages', label: 'Messages' },
      { href: '/admin/documents', label: 'Documents' },
    ],
  },
  {
    label: 'Knowledge',
    // The derived knowledge graph — what the system has learned from Activity.
    items: [
      { href: '/admin/claims', label: 'Claims' },
      { href: '/admin/gaps', label: 'Gaps' },
      { href: '/admin/contradictions', label: 'Contradictions' },
      { href: '/admin/brain', label: 'Brain' },
    ],
  },
  {
    label: 'Operations',
    // Operator tools — observability, taxonomy governance, system settings.
    items: [
      { href: '/admin/ai', label: 'AI Observability' },
      { href: '/admin/taxonomy', label: 'Taxonomy' },
      { href: '/admin/settings', label: 'Settings' },
    ],
  },
];

const EXTERNAL_LINK = { href: '/channels', label: '↗ Chat' };

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + '/');
}

export function AdminNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap items-baseline gap-x-3 gap-y-2 text-sm">
      {GROUPS.map((group, gi) => (
        <div key={group.label} className="flex items-baseline gap-3">
          {gi > 0 && (
            <span
              aria-hidden
              className="self-center h-4 w-px bg-border/70"
            />
          )}
          <span
            className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 select-none"
            title={`${group.label} section`}
          >
            {group.label}
          </span>
          <div className="flex items-baseline gap-2.5">
            {group.items.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'transition-colors',
                    active
                      ? 'font-semibold text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  aria-current={active ? 'page' : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
      <span
        aria-hidden
        className="self-center h-4 w-px bg-border/70"
      />
      <Link
        href={EXTERNAL_LINK.href}
        className="font-medium text-foreground hover:text-foreground/70"
        title="Go to chat rooms (leaves admin)"
      >
        {EXTERNAL_LINK.label}
      </Link>
    </nav>
  );
}
