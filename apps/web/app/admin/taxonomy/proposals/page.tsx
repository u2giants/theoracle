// R10.5 — Taxonomy proposals review queue.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ProposalListBulk } from './_components/proposal-list-bulk';

type ProposalRow = {
  id: string;
  proposal_type: string;
  payload: unknown;
  status: string;
  reviewed_by_employee_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  reviewer_name: string | null;
  apply_change_type: string | null;
  apply_reason: string | null;
  trigger_run_id: string | null;
  apply_retryable: boolean;
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
      e.name AS reviewer_name,
      apply_state.change_type AS apply_change_type,
      apply_state.reason AS apply_reason,
      apply_state.after_state->>'triggerRunId' AS trigger_run_id,
      COALESCE((apply_state.change_type = 'reclassification_failed'
        OR (apply_state.change_type = 'reclassification_dispatched'
          AND apply_state.created_at < now() - interval '15 minutes')), false) AS apply_retryable
    FROM taxonomy_proposals p
    LEFT JOIN employees e ON e.id = p.reviewed_by_employee_id
    LEFT JOIN LATERAL (
      SELECT cl.change_type, cl.reason, cl.after_state, cl.created_at
      FROM taxonomy_change_log cl
      WHERE cl.proposal_id = p.id
        AND (cl.change_type = 'reclassification_dispatched'
          OR cl.change_type LIKE 'reclassification_applied_%'
          OR cl.change_type LIKE 'reclassification_skipped_%'
          OR cl.change_type = 'reclassification_failed')
      ORDER BY cl.created_at DESC
      LIMIT 1
    ) apply_state ON true
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
          Compact proposal cards from the taxonomy re-evaluation worker. Approve to accept a
          proposal, then Apply to dispatch its audited reclassification. Reject records the decision
          without mutation. No auto-mutation: every taxonomy change is admin-gated.
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
        <ProposalListBulk proposals={rows} />
      )}
    </div>
  );
}
