// R10.5 — Entity proposals review queue.
// Surfaces unknown entities staged by extraction workers (R6 / R7) when
// the resolver returned 'unknown' or 'type_mismatch'. Admin approves
// (creates the canonical row) or rejects.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EntityProposalCard } from './_components/entity-proposal-card';

type EntityProposalRow = {
  id: string;
  proposed_entity_type: string;
  proposed_canonical_value: string;
  raw_strings_observed: unknown;
  proposed_aliases: unknown;
  proposed_domain_hints: unknown;
  observed_in_source_type: string;
  observed_in_source_id: string | null;
  status: string;
  merged_into_entity_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  reviewer_name: string | null;
};

const STATUS_TABS = [
  { value: 'pending', label: 'Pending review' },
  { value: 'approved', label: 'Approved' },
  { value: 'merged_into_existing', label: 'Merged' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'all', label: 'All' },
] as const;

export default async function AdminTaxonomyEntityProposalsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const params = await searchParams;
  const status = (params.status ?? 'pending') as (typeof STATUS_TABS)[number]['value'];
  const db = getDirectDb();

  const where = status === 'all' ? sql`` : sql`WHERE p.status = ${status}`;

  const result = await db.execute(sql`
    SELECT
      p.id, p.proposed_entity_type, p.proposed_canonical_value,
      p.raw_strings_observed, p.proposed_aliases, p.proposed_domain_hints,
      p.observed_in_source_type, p.observed_in_source_id,
      p.status, p.merged_into_entity_id, p.reviewed_at, p.created_at,
      e.name AS reviewer_name
    FROM entity_proposals p
    LEFT JOIN employees e ON e.id = p.reviewed_by_employee_id
    ${where}
    ORDER BY
      CASE WHEN p.status = 'pending' THEN 0 ELSE 1 END,
      p.created_at DESC
    LIMIT 100
  `);
  const rows = [...result] as unknown as EntityProposalRow[];

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Entity proposals</h1>
        <p className="text-sm text-muted-foreground">
          Unknown entities surfaced by extraction. Auto-creation is prohibited; each must
          be reviewed. Approving inserts (or merges with) the canonical{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">entities</code> row.
        </p>
      </header>

      <div className="flex flex-wrap gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === status;
          return (
            <a
              key={tab.value}
              href={`/admin/taxonomy/entity-proposals?status=${tab.value}`}
              className={`rounded px-3 py-1 ${
                isActive
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </a>
          );
        })}
      </div>

      {rows.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No entity proposals</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {status === 'pending'
              ? 'No proposals are waiting. The extraction workers stage these whenever they see an entity name that does not resolve in the registry.'
              : 'No proposals match the current filter.'}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => (
            <EntityProposalCard key={r.id} proposal={r} />
          ))}
        </div>
      )}
    </div>
  );
}
