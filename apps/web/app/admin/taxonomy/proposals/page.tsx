// R10.5 — Taxonomy proposals review queue.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ProposalCard } from './_components/proposal-card';

type ProposalRow = {
  id: string;
  proposal_type: string;
  payload: unknown;
  status: string;
  reviewed_by_employee_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  reviewer_name: string | null;
};

const STATUS_TABS = [
  { value: 'pending', label: 'Pending review' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'all', label: 'All' },
] as const;

export default async function AdminTaxonomyProposalsPage({
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
      p.id, p.proposal_type, p.payload, p.status,
      p.reviewed_by_employee_id, p.reviewed_at, p.created_at,
      e.name AS reviewer_name
    FROM taxonomy_proposals p
    LEFT JOIN employees e ON e.id = p.reviewed_by_employee_id
    ${where}
    ORDER BY
      CASE WHEN p.status = 'pending' THEN 0 ELSE 1 END,
      p.created_at DESC
    LIMIT 100
  `);
  const rows = [...result] as unknown as ProposalRow[];

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Taxonomy proposals</h1>
        <p className="text-sm text-muted-foreground">
          Compact proposal cards from the taxonomy re-evaluation worker. Approve to
          apply (with audit trail); reject to record the decision without mutation.
          No auto-mutation: every taxonomy change is admin-gated.
        </p>
      </header>

      <div className="flex gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === status;
          return (
            <a
              key={tab.value}
              href={`/admin/taxonomy/proposals?status=${tab.value}`}
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
            <CardTitle className="text-base">No proposals</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {status === 'pending'
              ? 'No proposals are waiting for review. The taxonomy-reevaluation worker writes new proposals when enough new evidence accumulates.'
              : 'No proposals match the current filter.'}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => (
            <ProposalCard key={r.id} proposal={r} />
          ))}
        </div>
      )}
    </div>
  );
}
