export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { updateContradictionStatus } from './_actions';

type ContradictionRow = {
  id: string;
  status: string;
  severity: string;
  description: string;
  detection_confidence: number | null;
  created_at: string;
  claim_a_id: string;
  claim_a_summary: string;
  claim_a_status: string;
  claim_b_id: string;
  claim_b_summary: string;
  claim_b_status: string;
  suggested_question: string | null;
};

const STATUS_TABS = [
  { label: 'Possible', value: 'possible' },
  { label: 'Open', value: 'open' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'All', value: 'all' },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    possible: 'bg-yellow-100 text-yellow-800',
    open: 'bg-orange-100 text-orange-800',
    resolved: 'bg-green-100 text-green-800',
    dismissed: 'bg-gray-100 text-gray-600',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

function severityBadge(severity: string) {
  const map: Record<string, string> = {
    low: 'bg-gray-100 text-gray-600',
    medium: 'bg-yellow-100 text-yellow-800',
    high: 'bg-orange-100 text-orange-800',
    critical: 'bg-red-100 text-red-800',
  };
  return map[severity] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminContradictionsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'possible';

  const db = getDirectDb();

  const whereClause =
    activeStatus !== 'all' ? sql`WHERE ctr.status = ${activeStatus}` : sql``;

  const result = await db.execute(sql`
    SELECT
      ctr.id,
      ctr.status,
      ctr.severity,
      ctr.description,
      ctr.detection_confidence,
      ctr.created_at,
      ctr.claim_a_id,
      ca.summary AS claim_a_summary,
      ca.status  AS claim_a_status,
      ctr.claim_b_id,
      cb.summary AS claim_b_summary,
      cb.status  AS claim_b_status,
      ctr.suggested_question
    FROM contradictions ctr
    JOIN claims ca ON ca.id = ctr.claim_a_id
    JOIN claims cb ON cb.id = ctr.claim_b_id
    ${whereClause}
    ORDER BY ctr.created_at DESC
  `);

  const rows = [...result] as unknown as ContradictionRow[];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Contradictions</h1>
        <p className="text-sm text-muted-foreground">
          Pairs of claims that conflict with each other. Confirm to escalate for Oracle
          follow-up; dismiss if the conflict is not material.
        </p>
      </header>

      <div className="flex gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === activeStatus;
          return (
            <Link
              key={tab.value}
              href={`/admin/contradictions?status=${tab.value}`}
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

      <div className="space-y-4">
        {rows.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No contradictions yet. The contradiction-watcher worker will flag conflicting
              claims once the extraction pipeline has run.
            </CardContent>
          </Card>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">{rows.length} contradictions</p>
            {rows.map((row) => (
              <Card key={row.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${severityBadge(row.severity)}`}
                      >
                        {row.severity}
                      </span>
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.status)}`}
                      >
                        {row.status}
                      </span>
                      {row.detection_confidence != null && (
                        <span className="text-xs text-muted-foreground">
                          {row.detection_confidence}% confidence
                        </span>
                      )}
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {new Date(row.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm">{row.description}</p>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded border p-3 text-sm">
                      <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                        Claim A
                      </p>
                      <p className="line-clamp-3">{row.claim_a_summary}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        status: {row.claim_a_status}
                      </p>
                    </div>
                    <div className="rounded border p-3 text-sm">
                      <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">
                        Claim B
                      </p>
                      <p className="line-clamp-3">{row.claim_b_summary}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        status: {row.claim_b_status}
                      </p>
                    </div>
                  </div>

                  {row.suggested_question && (
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">Suggested follow-up:</span>{' '}
                      {row.suggested_question}
                    </p>
                  )}

                  {['possible', 'open'].includes(row.status) && (
                    <div className="flex gap-2 pt-1">
                      {row.status === 'possible' && (
                        <form action={updateContradictionStatus}>
                          <input type="hidden" name="id" value={row.id} />
                          <input type="hidden" name="status" value="open" />
                          <button
                            type="submit"
                            className="rounded bg-orange-600 px-3 py-1 text-xs text-white hover:bg-orange-700"
                          >
                            Confirm
                          </button>
                        </form>
                      )}
                      <form action={updateContradictionStatus}>
                        <input type="hidden" name="id" value={row.id} />
                        <input type="hidden" name="status" value="dismissed" />
                        <button
                          type="submit"
                          className="rounded border px-3 py-1 text-xs hover:bg-muted"
                        >
                          Dismiss
                        </button>
                      </form>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
