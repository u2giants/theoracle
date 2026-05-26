// R10 — Paginated model_runs view.

export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatMs, formatPct, formatTokens } from '../_components/metric-card';

type RunRow = {
  model_run_id: string;
  task_type: string;
  route_id: string | null;
  provider: string;
  prompt_version: string | null;
  success: boolean;
  error: string | null;
  input_tokens: number | null;
  cached_input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  cache_hit_ratio: number | null;
  fell_back_from_route_id: string | null;
  fallback_reason: string | null;
  latency_ms: number | null;
  run_created_at: string;
};

const PAGE_SIZE = 50;
const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'success', label: 'Success only' },
  { value: 'failed', label: 'Failed only' },
  { value: 'fallback', label: 'Fallback dispatched' },
] as const;

export default async function AdminAIRunsPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string; task?: string; page?: string }>;
}) {
  const params = await searchParams;
  const filter = (params.filter ?? 'all') as (typeof FILTERS)[number]['value'];
  const taskFilter = params.task ?? '';
  const page = Math.max(1, Number(params.page ?? 1) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const db = getDirectDb();

  const filterSql =
    filter === 'success'
      ? sql`AND success = true`
      : filter === 'failed'
        ? sql`AND success = false`
        : filter === 'fallback'
          ? sql`AND fell_back_from_route_id IS NOT NULL`
          : sql``;
  const taskSql = taskFilter ? sql`AND task_type = ${taskFilter}` : sql``;

  const result = await db.execute(sql`
    SELECT
      model_run_id, task_type, route_id, provider, prompt_version,
      success, error,
      input_tokens, cached_input_tokens, output_tokens, reasoning_tokens,
      cache_hit_ratio, fell_back_from_route_id, fallback_reason,
      latency_ms, run_created_at
    FROM model_runs_with_usage
    WHERE 1=1 ${filterSql} ${taskSql}
    ORDER BY run_created_at DESC
    LIMIT ${PAGE_SIZE} OFFSET ${offset}
  `);

  const rows = [...result] as unknown as RunRow[];

  // Task type list for the filter UI.
  const taskListResult = await db.execute(sql`
    SELECT DISTINCT task_type FROM model_runs_with_usage ORDER BY task_type
  `);
  const taskTypes = ([...taskListResult] as unknown as Array<{ task_type: string }>).map(
    (r) => r.task_type,
  );

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Model runs</h1>
        <p className="text-sm text-muted-foreground">
          Every AI call through <code className="rounded bg-muted px-1 py-0.5 text-xs">OracleAIClient</code>.
          Each row links to its full context pack.
        </p>
      </header>

      <div className="flex flex-wrap gap-2 text-sm">
        {FILTERS.map((f) => {
          const active = f.value === filter;
          return (
            <Link
              key={f.value}
              href={`/admin/ai/runs?filter=${f.value}${taskFilter ? `&task=${taskFilter}` : ''}`}
              className={`rounded px-3 py-1 ${
                active
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {f.label}
            </Link>
          );
        })}
        {taskTypes.length > 0 && (
          <div className="ml-auto flex flex-wrap gap-2">
            <Link
              href={`/admin/ai/runs?filter=${filter}`}
              className={`rounded px-2 py-1 text-xs ${
                !taskFilter
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              all tasks
            </Link>
            {taskTypes.map((t) => (
              <Link
                key={t}
                href={`/admin/ai/runs?filter=${filter}&task=${t}`}
                className={`rounded px-2 py-1 text-xs ${
                  taskFilter === t
                    ? 'bg-foreground text-background'
                    : 'bg-muted text-muted-foreground hover:text-foreground'
                }`}
              >
                {t}
              </Link>
            ))}
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Showing {rows.length} run{rows.length === 1 ? '' : 's'} (page {page})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs match the current filters.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">When</th>
                  <th>Task</th>
                  <th>Route</th>
                  <th>Provider</th>
                  <th className="text-right">In</th>
                  <th className="text-right">Cached</th>
                  <th className="text-right">Out</th>
                  <th className="text-right">Hit ratio</th>
                  <th className="text-right">Latency</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.model_run_id} className="border-b align-top">
                    <td className="py-2 font-mono text-muted-foreground">
                      {new Date(r.run_created_at).toLocaleString()}
                    </td>
                    <td>{r.task_type}</td>
                    <td className="font-mono">
                      <Link
                        href={`/admin/ai/runs/${r.model_run_id}`}
                        className="text-foreground hover:underline"
                      >
                        {r.route_id ?? '(legacy)'}
                      </Link>
                      {r.fell_back_from_route_id && (
                        <div className="text-amber-600" title={r.fallback_reason ?? undefined}>
                          ↩ from {r.fell_back_from_route_id}
                        </div>
                      )}
                    </td>
                    <td className="text-muted-foreground">{r.provider}</td>
                    <td className="text-right">{formatTokens(r.input_tokens)}</td>
                    <td className="text-right">{formatTokens(r.cached_input_tokens)}</td>
                    <td className="text-right">{formatTokens(r.output_tokens)}</td>
                    <td className="text-right">{formatPct(r.cache_hit_ratio)}</td>
                    <td className="text-right">{formatMs(r.latency_ms)}</td>
                    <td>
                      {r.success ? (
                        <span className="rounded bg-green-100 px-1.5 py-0.5 text-green-800">ok</span>
                      ) : (
                        <span
                          className="rounded bg-red-100 px-1.5 py-0.5 text-red-800"
                          title={r.error ?? undefined}
                        >
                          fail
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-between text-sm">
        <Link
          href={`/admin/ai/runs?filter=${filter}${taskFilter ? `&task=${taskFilter}` : ''}&page=${Math.max(1, page - 1)}`}
          className={`rounded px-3 py-1 ${
            page > 1 ? 'bg-muted hover:bg-foreground hover:text-background' : 'pointer-events-none opacity-40'
          }`}
        >
          ← Previous
        </Link>
        <span className="text-muted-foreground">Page {page}</span>
        <Link
          href={`/admin/ai/runs?filter=${filter}${taskFilter ? `&task=${taskFilter}` : ''}&page=${page + 1}`}
          className={`rounded px-3 py-1 ${
            rows.length === PAGE_SIZE
              ? 'bg-muted hover:bg-foreground hover:text-background'
              : 'pointer-events-none opacity-40'
          }`}
        >
          Next →
        </Link>
      </div>
    </div>
  );
}
