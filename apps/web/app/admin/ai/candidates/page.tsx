// R10 — Extraction candidate review dashboard.
//
// Reads from extraction_candidates + extraction_validation_results.
// Lets the admin filter by status and drill into the validation reason
// for failed / sensitive candidates without exposing raw evidence text
// to the standard queue (sensitive candidates stay hidden by default).

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MetricCard } from '../_components/metric-card';

type CandidateRow = {
  id: string;
  status: string;
  claim_type: string;
  summary: string;
  impact_score: number;
  confidence_score: number | null;
  domains: unknown;
  stance: string | null;
  requires_review: boolean;
  review_reason: string | null;
  validation_error: string | null;
  promoted_to_claim_id: string | null;
  duplicate_of_claim_id: string | null;
  created_at: string;
  validated_at: string | null;
  promoted_at: string | null;
  validation_failures: number;
};

type StatusCountRow = { status: string; count: number };

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending_validation: 'bg-yellow-100 text-yellow-800',
    validated: 'bg-blue-100 text-blue-800',
    promoted: 'bg-green-100 text-green-800',
    duplicate: 'bg-gray-100 text-gray-700',
    validation_failed: 'bg-red-100 text-red-800',
    failed_validation_loop: 'bg-red-200 text-red-900',
    rejected: 'bg-gray-100 text-gray-600',
    rejected_sensitive: 'bg-purple-100 text-purple-800',
    quarantined_sensitive: 'bg-purple-200 text-purple-900',
  };
  return map[status] ?? 'bg-muted';
}

export default async function AdminAICandidatesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const params = await searchParams;
  const statusFilter = params.status ?? 'validation_failed';
  const db = getDirectDb();

  // The "sensitive" filter intentionally rolls up both rejected_sensitive
  // and quarantined_sensitive. Per spec: "Sensitive rejected/quarantined
  // candidates must not appear in this standard queue." We expose them
  // ONLY when the admin explicitly asks for the sensitive tab.
  const filterSql =
    statusFilter === 'all'
      ? sql`WHERE status NOT IN ('rejected_sensitive','quarantined_sensitive')`
      : statusFilter === 'sensitive'
        ? sql`WHERE status IN ('rejected_sensitive','quarantined_sensitive')`
        : sql`WHERE status = ${statusFilter}`;

  const [rowsResult, statusCountsResult] = await Promise.all([
    db.execute(sql`
      SELECT
        c.id, c.status, c.claim_type, c.summary,
        c.impact_score, c.confidence_score, c.domains, c.stance,
        c.requires_review, c.review_reason, c.validation_error,
        c.promoted_to_claim_id, c.duplicate_of_claim_id,
        c.created_at, c.validated_at, c.promoted_at,
        (
          SELECT COUNT(*)
          FROM extraction_validation_results vr
          WHERE vr.candidate_id = c.id AND vr.status IN ('fail','circuit_breaker')
        ) AS validation_failures
      FROM extraction_candidates c
      ${filterSql}
      ORDER BY c.created_at DESC
      LIMIT 100
    `),
    db.execute(sql`
      SELECT status, COUNT(*) AS count FROM extraction_candidates GROUP BY status
    `),
  ]);

  const rows = [...rowsResult] as unknown as CandidateRow[];
  const statusCounts = [...statusCountsResult] as unknown as StatusCountRow[];

  const STATUS_TABS = [
    { value: 'pending_validation', label: 'Pending' },
    { value: 'validated', label: 'Validated' },
    { value: 'promoted', label: 'Promoted' },
    { value: 'duplicate', label: 'Duplicate' },
    { value: 'validation_failed', label: 'Validation failed' },
    { value: 'failed_validation_loop', label: 'Circuit broken' },
    { value: 'sensitive', label: 'Sensitive (hidden by default)' },
    { value: 'all', label: 'All (non-sensitive)' },
  ] as const;

  const totals: Record<string, number> = {};
  for (const r of statusCounts) totals[r.status] = Number(r.count);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Extraction candidates</h1>
        <p className="text-sm text-muted-foreground">
          Staged outputs from extraction workers (R6/R7). Candidates promote to{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">claims</code> only after
          deterministic validation passes. Sensitive candidates are quarantined and never
          appear in the standard queue.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard title="Pending" value={totals['pending_validation'] ?? 0} />
        <MetricCard title="Promoted" value={totals['promoted'] ?? 0} />
        <MetricCard
          title="Validation failed"
          value={totals['validation_failed'] ?? 0}
          subtitle={`${totals['failed_validation_loop'] ?? 0} circuit-broken`}
        />
        <MetricCard
          title="Sensitive quarantined"
          value={
            (totals['rejected_sensitive'] ?? 0) + (totals['quarantined_sensitive'] ?? 0)
          }
        />
      </div>

      <div className="flex flex-wrap gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === statusFilter;
          return (
            <a
              key={tab.value}
              href={`/admin/ai/candidates?status=${tab.value}`}
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} candidate{rows.length === 1 ? '' : 's'}</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No candidates match the current filter.</p>
          ) : (
            <div className="space-y-3">
              {rows.map((r) => {
                const domains = Array.isArray(r.domains) ? (r.domains as string[]) : [];
                return (
                  <div key={r.id} className="rounded border bg-card p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 text-xs">
                          <span className={`rounded px-1.5 py-0.5 ${statusBadge(r.status)}`}>
                            {r.status}
                          </span>
                          <span className="font-mono text-muted-foreground">{r.claim_type}</span>
                          <span className="text-muted-foreground">
                            impact {r.impact_score}/10
                          </span>
                          {r.confidence_score != null && (
                            <span className="text-muted-foreground">
                              confidence {r.confidence_score}/10
                            </span>
                          )}
                          {r.stance && (
                            <span className="text-muted-foreground">stance: {r.stance}</span>
                          )}
                        </div>
                        <p className="mt-1 text-sm">{r.summary}</p>
                        {domains.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1 text-[10px]">
                            {domains.map((d) => (
                              <span
                                key={d}
                                className="rounded bg-muted px-1.5 py-0.5 font-mono text-muted-foreground"
                              >
                                {d}
                              </span>
                            ))}
                          </div>
                        )}
                        {r.validation_error && (
                          <div className="mt-2 rounded border-l-2 border-red-400 bg-red-50 p-2 text-xs">
                            <div className="font-semibold text-red-800">
                              Validation error
                              {r.validation_failures > 0 && (
                                <span className="ml-1 text-red-700">
                                  ({r.validation_failures} failed check
                                  {r.validation_failures === 1 ? '' : 's'})
                                </span>
                              )}
                            </div>
                            <div className="text-red-900">{r.validation_error}</div>
                          </div>
                        )}
                        {r.review_reason && (
                          <div className="mt-2 text-xs text-muted-foreground italic">
                            Review requested: {r.review_reason}
                          </div>
                        )}
                      </div>
                      <div className="text-right text-xs text-muted-foreground">
                        <div className="font-mono">{r.id.slice(0, 8)}…</div>
                        <div>{new Date(r.created_at).toLocaleString()}</div>
                        {r.promoted_to_claim_id && (
                          <div className="mt-1">
                            → <span className="font-mono">{r.promoted_to_claim_id.slice(0, 8)}…</span>
                          </div>
                        )}
                        {r.duplicate_of_claim_id && (
                          <div className="mt-1">
                            ⊃ <span className="font-mono">{r.duplicate_of_claim_id.slice(0, 8)}…</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
