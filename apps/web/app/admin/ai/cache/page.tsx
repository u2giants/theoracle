// R10 — Provider cache dashboard.
//
// Reads from provider_cached_content (R7 tracking table) and the
// model_runs_with_usage view for hit-ratio context.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';
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
  total_cache_write_tokens: number | null;
};

type ProviderRouteCacheRow = {
  provider: string;
  route_id: string | null;
  total_runs: number;
  total_input_tokens: number | null;
  total_cached_tokens: number | null;
  total_cache_write_tokens: number | null;
  weighted_hit_ratio: number | null;
  avg_hit_ratio: number | null;
};

type TaskRouteRow = {
  task_type: string;
  route_id: string | null;
  provider: string;
  total_runs: number;
  avg_hit_ratio: number | null;
  total_input_tokens: number | null;
  total_cached_tokens: number | null;
  total_cache_write_tokens: number | null;
};

type LowHitRow = {
  model_run_id: string;
  task_type: string;
  route_id: string | null;
  provider: string;
  input_tokens: number | null;
  cached_input_tokens: number | null;
  cache_hit_ratio: number | null;
  run_created_at: string;
};

type SummaryRow = {
  total_runs: number;
  avg_hit_ratio: number | null;
  total_cached_tokens: number | null;
  total_cache_write_tokens: number | null;
};

type ResponseSessionRow = {
  provider: string;
  session_key: string;
  scope_kind: string;
  scope_id: string;
  model_id: string;
  latest_response_id: string;
  updated_at: string;
};

type VertexFileCacheComparisonRow = {
  input_mode: string;
  task_type: string;
  route_id: string | null;
  provider: string;
  run_count: number;
  total_input_tokens: number | null;
  total_cached_tokens: number | null;
  total_cache_write_tokens: number | null;
  weighted_hit_ratio: number | null;
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

  const [
    rowsResult,
    statusCountsResult,
    providerHitResult,
    providerRouteCacheResult,
    taskRouteResult,
    lowHitResult,
    summaryResult,
    responseSessionsResult,
    vertexFileCacheComparisonResult,
  ] = await Promise.all([
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
             SUM(cached_input_tokens) AS total_cached_tokens,
             SUM(cache_write_tokens) AS total_cache_write_tokens
      FROM model_runs_with_usage
      WHERE run_created_at >= now() - interval '7 days'
      GROUP BY provider
      ORDER BY total_runs DESC
    `),
    db.execute(sql`
      SELECT provider,
             route_id,
             COUNT(*) AS total_runs,
             SUM(input_tokens) AS total_input_tokens,
             SUM(cached_input_tokens) AS total_cached_tokens,
             SUM(cache_write_tokens) AS total_cache_write_tokens,
             CASE
               WHEN COALESCE(SUM(input_tokens), 0) = 0
               THEN NULL
               ELSE COALESCE(SUM(cached_input_tokens), 0)::float / SUM(input_tokens)::float
             END AS weighted_hit_ratio,
             AVG(cache_hit_ratio) AS avg_hit_ratio
      FROM model_runs_with_usage
      WHERE run_created_at >= now() - interval '7 days'
      GROUP BY provider, route_id
      ORDER BY weighted_hit_ratio DESC NULLS LAST, total_input_tokens DESC NULLS LAST
      LIMIT 25
    `),
    db.execute(sql`
      SELECT task_type,
             route_id,
             provider,
             COUNT(*) AS total_runs,
             AVG(cache_hit_ratio) AS avg_hit_ratio,
             SUM(input_tokens) AS total_input_tokens,
             SUM(cached_input_tokens) AS total_cached_tokens,
             SUM(cache_write_tokens) AS total_cache_write_tokens
      FROM model_runs_with_usage
      WHERE run_created_at >= now() - interval '7 days'
      GROUP BY task_type, route_id, provider
      ORDER BY total_cached_tokens DESC NULLS LAST, total_runs DESC
      LIMIT 20
    `),
    db.execute(sql`
      SELECT model_run_id,
             task_type,
             route_id,
             provider,
             input_tokens,
             cached_input_tokens,
             cache_hit_ratio,
             run_created_at
      FROM model_runs_with_usage
      WHERE run_created_at >= now() - interval '7 days'
        AND input_tokens >= 4000
        AND COALESCE(cache_hit_ratio, 0) < 0.15
      ORDER BY input_tokens DESC, run_created_at DESC
      LIMIT 15
    `),
    db.execute(sql`
      SELECT COUNT(*) AS total_runs,
             AVG(cache_hit_ratio) AS avg_hit_ratio,
             SUM(cached_input_tokens) AS total_cached_tokens,
             SUM(cache_write_tokens) AS total_cache_write_tokens
      FROM model_runs_with_usage
      WHERE run_created_at >= now() - interval '7 days'
    `),
    db.execute(sql`
      SELECT provider,
             session_key,
             scope_kind,
             scope_id,
             model_id,
             latest_response_id,
             updated_at
      FROM provider_response_sessions
      ORDER BY updated_at DESC
      LIMIT 20
    `),
    db.execute(sql`
      WITH extraction_runs AS (
        SELECT
          mwu.model_run_id,
          mwu.task_type,
          mwu.route_id,
          mwu.provider,
          mwu.input_tokens,
          mwu.cached_input_tokens,
          mwu.cache_write_tokens,
          mwu.dispatch_mode,
          eb.job_run_id
        FROM model_runs_with_usage mwu
        JOIN extraction_batches eb ON eb.model_run_id = mwu.model_run_id
        WHERE mwu.run_created_at >= now() - interval '30 days'
          AND mwu.task_type IN ('claim-extraction', 'document-ingestion')
      )
      SELECT
        CASE
          WHEN EXISTS (
            SELECT 1
            FROM provider_cached_content pcc
            WHERE pcc.created_by_job_run_id = er.job_run_id
              AND pcc.provider = 'vertex'
              AND pcc.provider_metadata_json ? 'uploadedGcsUri'
          ) THEN 'file-backed cache'
          WHEN er.dispatch_mode = 'batch' THEN 'batch/plain'
          ELSE 'sync/plain'
        END AS input_mode,
        er.task_type,
        er.route_id,
        er.provider,
        COUNT(*) AS run_count,
        SUM(er.input_tokens) AS total_input_tokens,
        SUM(er.cached_input_tokens) AS total_cached_tokens,
        SUM(er.cache_write_tokens) AS total_cache_write_tokens,
        CASE
          WHEN COALESCE(SUM(er.input_tokens), 0) = 0
          THEN NULL
          ELSE COALESCE(SUM(er.cached_input_tokens), 0)::float / SUM(er.input_tokens)::float
        END AS weighted_hit_ratio
      FROM extraction_runs er
      GROUP BY 1, er.task_type, er.route_id, er.provider
      ORDER BY total_input_tokens DESC NULLS LAST, run_count DESC
      LIMIT 20
    `),
  ]);

  const rows = [...rowsResult] as unknown as CacheRow[];
  const statusCounts = [...statusCountsResult] as unknown as StatusCountRow[];
  const providerHit = [...providerHitResult] as unknown as ProviderRow[];
  const providerRouteCache = [...providerRouteCacheResult] as unknown as ProviderRouteCacheRow[];
  const taskRouteRows = [...taskRouteResult] as unknown as TaskRouteRow[];
  const lowHitRows = [...lowHitResult] as unknown as LowHitRow[];
  const summary = ([...summaryResult] as unknown as SummaryRow[])[0];
  const responseSessions = [...responseSessionsResult] as unknown as ResponseSessionRow[];
  const vertexFileCacheComparison =
    [...vertexFileCacheComparisonResult] as unknown as VertexFileCacheComparisonRow[];

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

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard title="Runs (7d)" value={Number(summary?.total_runs ?? 0)} />
        <MetricCard title="Avg hit ratio" value={formatPct(summary?.avg_hit_ratio)} />
        <MetricCard title="Cached tokens (7d)" value={formatTokens(Number(summary?.total_cached_tokens ?? 0))} />
        <MetricCard title="Cache writes (7d)" value={formatTokens(Number(summary?.total_cache_write_tokens ?? 0))} />
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
                  <th className="text-right">Cache write tokens</th>
                </tr>
              </thead>
              <tbody>
                {providerHit.map((p) => (
                  <tr key={p.provider} className="border-b">
                    <td className="py-2">{p.provider}</td>
                    <td className="text-right">{Number(p.total_runs)}</td>
                    <td className="text-right">{formatPct(p.avg_hit_ratio)}</td>
                    <td className="text-right">{formatTokens(Number(p.total_cached_tokens ?? 0))}</td>
                    <td className="text-right">{formatTokens(Number(p.total_cache_write_tokens ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Provider / route cache share (last 7 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {providerRouteCache.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs in the last 7 days yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Provider</th>
                  <th>Route</th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Input tokens</th>
                  <th className="text-right">Cached tokens</th>
                  <th className="text-right">Weighted hit ratio</th>
                  <th className="text-right">Avg hit ratio</th>
                  <th className="text-right">Cache writes</th>
                </tr>
              </thead>
              <tbody>
                {providerRouteCache.map((row) => (
                  <tr key={`${row.provider}:${row.route_id ?? 'none'}`} className="border-b">
                    <td className="py-2">{row.provider}</td>
                    <td className="max-w-sm truncate text-muted-foreground" title={row.route_id ?? undefined}>
                      {row.route_id ?? '—'}
                    </td>
                    <td className="text-right">{Number(row.total_runs)}</td>
                    <td className="text-right">{formatTokens(Number(row.total_input_tokens ?? 0))}</td>
                    <td className="text-right">{formatTokens(Number(row.total_cached_tokens ?? 0))}</td>
                    <td className="text-right">{formatPct(row.weighted_hit_ratio)}</td>
                    <td className="text-right">{formatPct(row.avg_hit_ratio)}</td>
                    <td className="text-right">{formatTokens(Number(row.total_cache_write_tokens ?? 0))}</td>
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
          <CardTitle className="text-base">Task / route efficiency (last 7 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {taskRouteRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No cacheable runs in the last 7 days yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Task</th>
                  <th>Route</th>
                  <th>Provider</th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Avg hit ratio</th>
                  <th className="text-right">Input tokens</th>
                  <th className="text-right">Cached tokens</th>
                  <th className="text-right">Cache writes</th>
                </tr>
              </thead>
              <tbody>
                {taskRouteRows.map((row) => (
                  <tr key={`${row.task_type}:${row.route_id ?? 'none'}:${row.provider}`} className="border-b">
                    <td className="py-2">{row.task_type}</td>
                    <td className="max-w-xs truncate text-muted-foreground" title={row.route_id ?? undefined}>
                      {row.route_id ?? '—'}
                    </td>
                    <td>{row.provider}</td>
                    <td className="text-right">{Number(row.total_runs)}</td>
                    <td className="text-right">{formatPct(row.avg_hit_ratio)}</td>
                    <td className="text-right">{formatTokens(Number(row.total_input_tokens ?? 0))}</td>
                    <td className="text-right">{formatTokens(Number(row.total_cached_tokens ?? 0))}</td>
                    <td className="text-right">{formatTokens(Number(row.total_cache_write_tokens ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">High-cost, low-hit runs (last 7 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {lowHitRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No large low-hit runs in the last 7 days.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Task</th>
                  <th>Route</th>
                  <th>Provider</th>
                  <th className="text-right">Input tokens</th>
                  <th className="text-right">Cached tokens</th>
                  <th className="text-right">Hit ratio</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {lowHitRows.map((row) => (
                  <tr key={row.model_run_id} className="border-b">
                    <td className="py-2">{row.task_type}</td>
                    <td className="max-w-xs truncate text-muted-foreground" title={row.route_id ?? undefined}>
                      {row.route_id ?? '—'}
                    </td>
                    <td>{row.provider}</td>
                    <td className="text-right">{formatTokens(row.input_tokens)}</td>
                    <td className="text-right">{formatTokens(row.cached_input_tokens)}</td>
                    <td className="text-right">{formatPct(row.cache_hit_ratio)}</td>
                    <td className="text-muted-foreground">
                      {formatNYDateTime(row.run_created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">File-backed cache vs plain extraction input (last 30 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {vertexFileCacheComparison.length === 0 ? (
            <p className="text-sm text-muted-foreground">No extraction runs in the last 30 days.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Input mode</th>
                  <th>Task</th>
                  <th>Route</th>
                  <th>Provider</th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Input tokens</th>
                  <th className="text-right">Cached tokens</th>
                  <th className="text-right">Weighted hit ratio</th>
                  <th className="text-right">Cache writes</th>
                </tr>
              </thead>
              <tbody>
                {vertexFileCacheComparison.map((row) => (
                  <tr
                    key={`${row.input_mode}:${row.task_type}:${row.route_id ?? 'none'}:${row.provider}`}
                    className="border-b"
                  >
                    <td className="py-2">{row.input_mode}</td>
                    <td>{row.task_type}</td>
                    <td className="max-w-xs truncate text-muted-foreground" title={row.route_id ?? undefined}>
                      {row.route_id ?? '—'}
                    </td>
                    <td>{row.provider}</td>
                    <td className="text-right">{Number(row.run_count)}</td>
                    <td className="text-right">{formatTokens(Number(row.total_input_tokens ?? 0))}</td>
                    <td className="text-right">{formatTokens(Number(row.total_cached_tokens ?? 0))}</td>
                    <td className="text-right">{formatPct(row.weighted_hit_ratio)}</td>
                    <td className="text-right">{formatTokens(Number(row.total_cache_write_tokens ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Provider response sessions ({responseSessions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {responseSessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No provider response sessions have been recorded.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Provider</th>
                  <th>Session</th>
                  <th>Scope</th>
                  <th>Model</th>
                  <th>Latest response</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {responseSessions.map((row) => (
                  <tr key={`${row.provider}:${row.session_key}`} className="border-b">
                    <td className="py-2">{row.provider}</td>
                    <td className="max-w-xs truncate font-mono text-muted-foreground" title={row.session_key}>
                      {row.session_key}
                    </td>
                    <td>{row.scope_kind}:{row.scope_id}</td>
                    <td className="max-w-xs truncate text-muted-foreground" title={row.model_id}>
                      {row.model_id}
                    </td>
                    <td className="max-w-xs truncate font-mono text-muted-foreground" title={row.latest_response_id}>
                      {row.latest_response_id}
                    </td>
                    <td className="text-muted-foreground">{formatNYDateTime(row.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

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
                      {formatNYDateTime(r.hard_expiration_at)}
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
