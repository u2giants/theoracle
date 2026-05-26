// R10 — Provider cache dashboard.
//
// Reads from provider_cached_content (R7 tracking table) and the
// model_runs_with_usage view for hit-ratio context.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MetricCard, formatPct, formatTokens } from '../_components/metric-card';

type CacheRow = {
  id: string;
  provider: string;
  cache_kind: string;
  source_description: string | null;
  source_token_estimate: number | null;
  expected_reuse_count: number;
  actual_reuse_count: number;
  latest_planned_reuse_step: string | null;
  hard_expiration_at: string;
  cleanup_owner: string | null;
  status: string;
  deleted_at: string | null;
  status_reason: string | null;
  created_at: string;
};

type StatusCountRow = { status: string; count: number };
type ProviderRow = {
  provider: string;
  total_runs: number;
  avg_hit_ratio: number | null;
  total_cached_tokens: number | null;
};

function statusBadge(status: string) {
  const map: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    deleted: 'bg-gray-100 text-gray-700',
    expired: 'bg-amber-100 text-amber-800',
    failed: 'bg-red-100 text-red-800',
    orphaned: 'bg-purple-100 text-purple-800',
  };
  return map[status] ?? 'bg-muted';
}

export default async function AdminAICachePage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const params = await searchParams;
  const statusFilter = params.status ?? 'active';
  const db = getDirectDb();

  const filterSql = statusFilter === 'all' ? sql`` : sql`WHERE status = ${statusFilter}`;

  const [rowsResult, statusCountsResult, providerHitResult] = await Promise.all([
    db.execute(sql`
      SELECT id, provider, cache_kind, source_description, source_token_estimate,
             expected_reuse_count, actual_reuse_count, latest_planned_reuse_step,
             hard_expiration_at, cleanup_owner, status, deleted_at, status_reason, created_at
      FROM provider_cached_content
      ${filterSql}
      ORDER BY created_at DESC
      LIMIT 100
    `),
    db.execute(sql`
      SELECT status, COUNT(*) AS count FROM provider_cached_content GROUP BY status
    `),
    db.execute(sql`
      SELECT provider,
             COUNT(*) AS total_runs,
             AVG(cache_hit_ratio) AS avg_hit_ratio,
             SUM(cached_input_tokens) AS total_cached_tokens
      FROM model_runs_with_usage
      WHERE run_created_at >= now() - interval '7 days'
      GROUP BY provider
      ORDER BY total_runs DESC
    `),
  ]);

  const rows = [...rowsResult] as unknown as CacheRow[];
  const statusCounts = [...statusCountsResult] as unknown as StatusCountRow[];
  const providerHit = [...providerHitResult] as unknown as ProviderRow[];

  const STATUS_TABS = [
    { value: 'all', label: 'All' },
    { value: 'active', label: 'Active' },
    { value: 'deleted', label: 'Deleted' },
    { value: 'expired', label: 'Expired' },
    { value: 'failed', label: 'Failed' },
    { value: 'orphaned', label: 'Orphaned' },
  ] as const;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Provider cache</h1>
        <p className="text-sm text-muted-foreground">
          Tracked explicit caches from{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">provider_cached_content</code>{' '}
          plus implicit-cache hit ratios from{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">model_runs_with_usage</code>.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {STATUS_TABS.filter((t) => t.value !== 'all').map((t) => {
          const count = statusCounts.find((c) => c.status === t.value)?.count ?? 0;
          return <MetricCard key={t.value} title={t.label} value={Number(count)} />;
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Provider hit ratio (last 7 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {providerHit.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs in the last 7 days yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Provider</th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Avg hit ratio</th>
                  <th className="text-right">Total cached tokens</th>
                </tr>
              </thead>
              <tbody>
                {providerHit.map((p) => (
                  <tr key={p.provider} className="border-b">
                    <td className="py-2">{p.provider}</td>
                    <td className="text-right">{Number(p.total_runs)}</td>
                    <td className="text-right">{formatPct(p.avg_hit_ratio)}</td>
                    <td className="text-right">{formatTokens(Number(p.total_cached_tokens ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === statusFilter;
          return (
            <a
              key={tab.value}
              href={`/admin/ai/cache?status=${tab.value}`}
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
          <CardTitle className="text-base">Cache rows ({rows.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No cache rows match the current filter.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Provider</th>
                  <th>Kind</th>
                  <th>Source</th>
                  <th className="text-right">Tokens</th>
                  <th className="text-right">Reuse</th>
                  <th>Hard expiration</th>
                  <th>Cleanup owner</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b">
                    <td className="py-2">{r.provider}</td>
                    <td>{r.cache_kind}</td>
                    <td className="max-w-xs truncate text-muted-foreground" title={r.source_description ?? undefined}>
                      {r.source_description ?? '—'}
                    </td>
                    <td className="text-right">{formatTokens(r.source_token_estimate)}</td>
                    <td className="text-right">
                      {r.actual_reuse_count} / {r.expected_reuse_count}
                    </td>
                    <td className="font-mono text-muted-foreground">
                      {new Date(r.hard_expiration_at).toLocaleString()}
                    </td>
                    <td>{r.cleanup_owner ?? '—'}</td>
                    <td>
                      <span className={`rounded px-1.5 py-0.5 ${statusBadge(r.status)}`} title={r.status_reason ?? undefined}>
                        {r.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
