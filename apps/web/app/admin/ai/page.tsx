// R10 — AI observability home page.
//
// Shows top-level metrics across the AI pipeline:
//   - Total runs in the last 24h / 7d
//   - Average cache hit ratio (from model_runs_with_usage view)
//   - Fallback dispatch rate
//   - Active provider caches
//   - Pending extraction candidates
//   - Recent runs table with drill-down to /admin/ai/runs/[id]
//
// All data is read-only and server-rendered. No new schema; all queries
// hit views and tables shipped by R3/R3.5/R4/R7.

export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MetricCard, formatPct, formatTokens, formatMs } from './_components/metric-card';

type SummaryRow = {
  total_runs_24h: number;
  total_runs_7d: number;
  successful_runs_7d: number;
  failed_runs_7d: number;
  avg_cache_hit_ratio_7d: number | null;
  avg_input_tokens_7d: number | null;
  avg_output_tokens_7d: number | null;
  avg_latency_ms_7d: number | null;
  fallback_runs_7d: number;
};

type RouteUsageRow = {
  route_id: string | null;
  task_type: string;
  provider: string;
  run_count: number;
  avg_input_tokens: number | null;
  avg_cached_input_tokens: number | null;
  avg_cache_hit_ratio: number | null;
  success_rate: number | null;
};

type RecentRunRow = {
  model_run_id: string;
  task_type: string;
  route_id: string | null;
  provider: string;
  success: boolean;
  input_tokens: number | null;
  cached_input_tokens: number | null;
  output_tokens: number | null;
  cache_hit_ratio: number | null;
  fell_back_from_route_id: string | null;
  latency_ms: number | null;
  run_created_at: string;
};

type CandidateCountRow = { status: string; count: number };
type CacheCountRow = { status: string; count: number };

export default async function AdminAIPage() {
  const db = getDirectDb();

  // Summary row aggregated across the last 7 days.
  const [summaryResult, routeUsageResult, recentRunsResult, candidateCountsResult, cacheCountsResult] =
    await Promise.all([
      db.execute(sql`
        SELECT
          COUNT(*) FILTER (WHERE run_created_at >= now() - interval '24 hours') AS total_runs_24h,
          COUNT(*) FILTER (WHERE run_created_at >= now() - interval '7 days') AS total_runs_7d,
          COUNT(*) FILTER (WHERE success = true AND run_created_at >= now() - interval '7 days') AS successful_runs_7d,
          COUNT(*) FILTER (WHERE success = false AND run_created_at >= now() - interval '7 days') AS failed_runs_7d,
          AVG(cache_hit_ratio) FILTER (WHERE run_created_at >= now() - interval '7 days') AS avg_cache_hit_ratio_7d,
          AVG(input_tokens) FILTER (WHERE run_created_at >= now() - interval '7 days') AS avg_input_tokens_7d,
          AVG(output_tokens) FILTER (WHERE run_created_at >= now() - interval '7 days') AS avg_output_tokens_7d,
          AVG(latency_ms) FILTER (WHERE run_created_at >= now() - interval '7 days') AS avg_latency_ms_7d,
          COUNT(*) FILTER (WHERE fell_back_from_route_id IS NOT NULL AND run_created_at >= now() - interval '7 days') AS fallback_runs_7d
        FROM model_runs_with_usage
      `),
      db.execute(sql`
        SELECT
          route_id,
          task_type,
          provider,
          COUNT(*) AS run_count,
          AVG(input_tokens) AS avg_input_tokens,
          AVG(cached_input_tokens) AS avg_cached_input_tokens,
          AVG(cache_hit_ratio) AS avg_cache_hit_ratio,
          AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate
        FROM model_runs_with_usage
        WHERE run_created_at >= now() - interval '7 days'
        GROUP BY route_id, task_type, provider
        ORDER BY run_count DESC
        LIMIT 20
      `),
      db.execute(sql`
        SELECT
          model_run_id,
          task_type,
          route_id,
          provider,
          success,
          input_tokens,
          cached_input_tokens,
          output_tokens,
          cache_hit_ratio,
          fell_back_from_route_id,
          latency_ms,
          run_created_at
        FROM model_runs_with_usage
        ORDER BY run_created_at DESC
        LIMIT 25
      `),
      db.execute(sql`
        SELECT status, COUNT(*) AS count
        FROM extraction_candidates
        GROUP BY status
      `),
      db.execute(sql`
        SELECT status, COUNT(*) AS count
        FROM provider_cached_content
        GROUP BY status
      `),
    ]);

  const summary = ([...summaryResult] as unknown as SummaryRow[])[0];
  const routeUsage = [...routeUsageResult] as unknown as RouteUsageRow[];
  const recentRuns = [...recentRunsResult] as unknown as RecentRunRow[];
  const candidateCounts = [...candidateCountsResult] as unknown as CandidateCountRow[];
  const cacheCounts = [...cacheCountsResult] as unknown as CacheCountRow[];

  const totalRuns7d = Number(summary?.total_runs_7d ?? 0);
  const successfulRuns7d = Number(summary?.successful_runs_7d ?? 0);
  const failedRuns7d = Number(summary?.failed_runs_7d ?? 0);
  const fallbackRuns7d = Number(summary?.fallback_runs_7d ?? 0);
  const successRate = totalRuns7d > 0 ? successfulRuns7d / totalRuns7d : null;
  const fallbackRate = totalRuns7d > 0 ? fallbackRuns7d / totalRuns7d : null;

  const pendingCandidates =
    candidateCounts.find((r) => r.status === 'pending_validation')?.count ?? 0;
  const promotedCandidates = candidateCounts.find((r) => r.status === 'promoted')?.count ?? 0;
  const failedCandidates =
    candidateCounts.find((r) => r.status === 'validation_failed')?.count ?? 0;
  const sensitiveCandidates = candidateCounts
    .filter((r) => r.status === 'rejected_sensitive' || r.status === 'quarantined_sensitive')
    .reduce((sum, r) => sum + Number(r.count), 0);

  const activeCaches = cacheCounts.find((r) => r.status === 'active')?.count ?? 0;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">AI Observability</h1>
        <p className="text-sm text-muted-foreground">
          Live view of the OracleAIClient pipeline. Reads from{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">model_runs_with_usage</code> view
          plus the R4 staging + R7 cache tracking tables.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          title="Model runs (24h)"
          value={Number(summary?.total_runs_24h ?? 0)}
          subtitle={`${totalRuns7d} in last 7 days`}
        />
        <MetricCard
          title="Success rate (7d)"
          value={formatPct(successRate)}
          subtitle={`${failedRuns7d} failed / ${totalRuns7d} total`}
          trend={successRate != null && successRate >= 0.95 ? 'up' : 'down'}
        />
        <MetricCard
          title="Cache hit ratio (7d)"
          value={formatPct(summary?.avg_cache_hit_ratio_7d ?? null)}
          subtitle="Average across all routes"
          trend={(summary?.avg_cache_hit_ratio_7d ?? 0) >= 0.5 ? 'up' : 'down'}
        />
        <MetricCard
          title="Fallback rate (7d)"
          value={formatPct(fallbackRate)}
          subtitle={`${fallbackRuns7d} runs hit a fallback route`}
          trend={fallbackRate != null && fallbackRate < 0.05 ? 'up' : 'down'}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          title="Avg input tokens (7d)"
          value={formatTokens(summary?.avg_input_tokens_7d ?? null)}
        />
        <MetricCard
          title="Avg output tokens (7d)"
          value={formatTokens(summary?.avg_output_tokens_7d ?? null)}
        />
        <MetricCard
          title="Avg latency (7d)"
          value={formatMs(summary?.avg_latency_ms_7d ?? null)}
        />
        <MetricCard
          title="Active provider caches"
          value={Number(activeCaches)}
          subtitle="From provider_cached_content"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <MetricCard title="Pending candidates" value={Number(pendingCandidates)} />
        <MetricCard title="Promoted to claims" value={Number(promotedCandidates)} />
        <MetricCard
          title="Failed validation"
          value={Number(failedCandidates)}
          trend={Number(failedCandidates) === 0 ? 'up' : 'down'}
        />
        <MetricCard
          title="Sensitive quarantined"
          value={Number(sensitiveCandidates)}
          subtitle="Never reach claims by design"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-6 text-xs">
        <Link href="/admin/ai/runs" className="rounded border bg-card p-3 hover:bg-muted">
          <div className="font-semibold">Model runs →</div>
          <div className="text-muted-foreground">Paginated view of every AI call.</div>
        </Link>
        <Link href="/admin/ai/candidates" className="rounded border bg-card p-3 hover:bg-muted">
          <div className="font-semibold">Extraction candidates →</div>
          <div className="text-muted-foreground">Review failed + sensitive candidates.</div>
        </Link>
        <Link href="/admin/ai/cache" className="rounded border bg-card p-3 hover:bg-muted">
          <div className="font-semibold">Provider cache →</div>
          <div className="text-muted-foreground">Active / deleted / orphaned caches.</div>
        </Link>
        <Link href="/admin/ai/evals" className="rounded border bg-card p-3 hover:bg-muted">
          <div className="font-semibold">Evals (placeholder) →</div>
          <div className="text-muted-foreground">Eval results will land here.</div>
        </Link>
        <Link href="/admin/ai/claim-lessons" className="rounded border bg-card p-3 hover:bg-muted">
          <div className="font-semibold">Claim lessons →</div>
          <div className="text-muted-foreground">Approved revisions that steer future extraction.</div>
        </Link>
        <Link href="/admin/ai/extraction-ab" className="rounded border bg-card p-3 hover:bg-muted">
          <div className="font-semibold">Extraction A/B/C →</div>
          <div className="text-muted-foreground">Score Gemini 2.5 vs 3.1, Qwen, and your revision.</div>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Route usage (last 7 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {routeUsage.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs in the last 7 days yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Route</th>
                  <th>Task</th>
                  <th>Provider</th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Avg input</th>
                  <th className="text-right">Cache hit</th>
                  <th className="text-right">Success</th>
                </tr>
              </thead>
              <tbody>
                {routeUsage.map((r) => (
                  <tr key={`${r.route_id ?? 'legacy'}-${r.task_type}-${r.provider}`} className="border-b">
                    <td className="py-2 font-mono">{r.route_id ?? '(legacy)'}</td>
                    <td className="text-muted-foreground">{r.task_type}</td>
                    <td className="text-muted-foreground">{r.provider}</td>
                    <td className="text-right">{Number(r.run_count)}</td>
                    <td className="text-right">{formatTokens(Number(r.avg_input_tokens))}</td>
                    <td className="text-right">{formatPct(r.avg_cache_hit_ratio)}</td>
                    <td className="text-right">{formatPct(r.success_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent model runs</CardTitle>
        </CardHeader>
        <CardContent>
          {recentRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No model runs logged yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">When</th>
                  <th>Task</th>
                  <th>Route</th>
                  <th className="text-right">In</th>
                  <th className="text-right">Cached</th>
                  <th className="text-right">Out</th>
                  <th className="text-right">Latency</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((r) => (
                  <tr key={r.model_run_id} className="border-b">
                    <td className="py-2 font-mono text-muted-foreground">
                      {new Date(r.run_created_at).toLocaleString()}
                    </td>
                    <td>{r.task_type}</td>
                    <td className="font-mono">
                      <Link
                        href={`/admin/ai/runs/${r.model_run_id}`}
                        className="text-foreground hover:underline"
                      >
                        {r.route_id ?? `(${r.provider})`}
                      </Link>
                      {r.fell_back_from_route_id && (
                        <span className="ml-1 text-amber-600" title={`fell back from ${r.fell_back_from_route_id}`}>
                          ↩
                        </span>
                      )}
                    </td>
                    <td className="text-right">{formatTokens(r.input_tokens)}</td>
                    <td className="text-right">{formatTokens(r.cached_input_tokens)}</td>
                    <td className="text-right">{formatTokens(r.output_tokens)}</td>
                    <td className="text-right">{formatMs(r.latency_ms)}</td>
                    <td>
                      {r.success ? (
                        <span className="rounded bg-green-100 px-1.5 py-0.5 text-green-800">ok</span>
                      ) : (
                        <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-800">fail</span>
                      )}
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
