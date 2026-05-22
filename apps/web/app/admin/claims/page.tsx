export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { updateClaimStatus } from './_actions';

type ClaimRow = {
  id: string;
  summary: string;
  claim_type: string;
  status: string;
  impact_score: number;
  confidence_score: number;
  created_at: string;
  exact_quote: string | null;
  source_type: string | null;
  employee_name: string | null;
};

const STATUS_TABS = [
  { label: 'Pending review', value: 'pending_review' },
  { label: 'Approved', value: 'approved' },
  { label: 'Rejected', value: 'rejected' },
  { label: 'All', value: 'all' },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending_review: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    superseded: 'bg-gray-100 text-gray-600',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminClaimsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'pending_review';

  const db = getDirectDb();

  const whereClause =
    activeStatus !== 'all' ? sql`WHERE c.status = ${activeStatus}` : sql``;

  const result = await db.execute(sql`
    SELECT
      c.id,
      c.summary,
      c.claim_type,
      c.status,
      c.impact_score,
      c.confidence_score,
      c.created_at,
      ce.exact_quote,
      ce.source_type,
      e.name AS employee_name
    FROM claims c
    LEFT JOIN LATERAL (
      SELECT exact_quote, source_type, asserted_by_employee_id
      FROM claim_evidence
      WHERE claim_id = c.id
      ORDER BY confidence DESC NULLS LAST, created_at ASC
      LIMIT 1
    ) ce ON true
    LEFT JOIN employees e ON e.id = ce.asserted_by_employee_id
    ${whereClause}
    ORDER BY c.created_at DESC
  `);

  const rows = result.rows as ClaimRow[];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Claims</h1>
        <p className="text-sm text-muted-foreground">
          Review extracted claims. Approving a claim makes it eligible for brain section
          synthesis.
        </p>
      </header>

      <div className="flex gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === activeStatus;
          return (
            <Link
              key={tab.value}
              href={`/admin/claims?status=${tab.value}`}
              className={`rounded px-3 py-1 ${
                isActive
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} claims</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No claims yet. Workers will populate this table once messages have been
              processed by the extraction worker.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Summary</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Impact</th>
                    <th className="py-2 pr-4">Confidence</th>
                    <th className="py-2 pr-4">Employee</th>
                    <th className="py-2 pr-4">Evidence</th>
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-3 pr-4 max-w-xs">
                        <span className="line-clamp-2">{row.summary}</span>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                        {row.claim_type}
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.status)}`}
                        >
                          {row.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-center">{row.impact_score}</td>
                      <td className="py-3 pr-4 text-center">{row.confidence_score}</td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        {row.employee_name ?? '—'}
                      </td>
                      <td className="py-3 pr-4 max-w-xs text-xs text-muted-foreground">
                        {row.exact_quote ? (
                          <span className="line-clamp-2 italic">
                            &ldquo;{row.exact_quote}&rdquo;
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                        {new Date(row.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3">
                        {row.status === 'pending_review' && (
                          <div className="flex gap-2">
                            <form action={updateClaimStatus}>
                              <input type="hidden" name="id" value={row.id} />
                              <input type="hidden" name="status" value="approved" />
                              <button
                                type="submit"
                                className="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                              >
                                Approve
                              </button>
                            </form>
                            <form action={updateClaimStatus}>
                              <input type="hidden" name="id" value={row.id} />
                              <input type="hidden" name="status" value="rejected" />
                              <button
                                type="submit"
                                className="rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700"
                              >
                                Reject
                              </button>
                            </form>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
