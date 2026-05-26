// R10 — Model run detail + context pack viewer.
//
// Shows everything we recorded for one AI call:
//   - Route, provider, prompt version
//   - Full OracleUsage breakdown
//   - The full prompt plan (block-by-block) from oracle_context_packs.blocks_json
//   - Retrieval observability: which domains/source types/process stages/
//     entities were selected, which message/chunk/claim/gap/contradiction
//     IDs were included
//   - Any extraction_batches that referenced this run
//   - Any provider_cached_content rows created in this run

export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatMs, formatPct, formatTokens } from '../../_components/metric-card';

type RunDetail = {
  model_run_id: string;
  task_type: string;
  model: string;
  provider: string;
  prompt_version: string | null;
  legacy_input_tokens: number | null;
  legacy_output_tokens: number | null;
  cost_usd: string | null;
  latency_ms: number | null;
  success: boolean;
  error: string | null;
  run_created_at: string;
  usage_detail_id: string | null;
  route_id: string | null;
  input_tokens: number | null;
  cached_input_tokens: number | null;
  cache_write_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  provider_request_id: string | null;
  fell_back_from_route_id: string | null;
  fallback_reason: string | null;
  context_pack_id: string | null;
  stable_prefix_hash: string | null;
  dynamic_input_hash: string | null;
  retrieval_plan_id: string | null;
  selected_domains: unknown;
  included_message_ids: unknown;
  included_document_chunk_ids: unknown;
  included_claim_ids: unknown;
  cache_hit_ratio: number | null;
};

type ContextPackDetail = {
  id: string;
  blocks_json: unknown;
  semi_stable_context_hash: string | null;
  retrieved_context_hash: string | null;
  tool_schema_hash: string | null;
  output_schema_hash: string | null;
  selected_source_types: unknown;
  selected_process_stages: unknown;
  selected_entity_ids: unknown;
  included_gap_ids: unknown;
  included_contradiction_ids: unknown;
  schema_version: string | null;
};

type BlockJson = {
  id: string;
  label: string;
  kind: string;
  hash: string;
  tokenEstimate: number | null;
  cacheEligible: boolean;
  reasonIncluded: string;
};

type ExtractionBatchRef = {
  id: string;
  status: string;
  batch_type: string;
  source_hash: string;
  validation_attempt_count: number;
  consecutive_quote_failure_count: number;
  created_at: string;
};

type CacheRef = {
  id: string;
  provider: string;
  cache_kind: string;
  source_description: string | null;
  expected_reuse_count: number;
  actual_reuse_count: number;
  status: string;
  hard_expiration_at: string;
  deleted_at: string | null;
};

export default async function AdminAIRunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const db = getDirectDb();

  const result = await db.execute(sql`
    SELECT *
    FROM model_runs_with_usage
    WHERE model_run_id = ${id}
    LIMIT 1
  `);
  const run = ([...result] as unknown as RunDetail[])[0];
  if (!run) return notFound();

  let contextPack: ContextPackDetail | undefined;
  let blocks: BlockJson[] = [];
  if (run.context_pack_id) {
    const cpResult = await db.execute(sql`
      SELECT id, blocks_json,
             semi_stable_context_hash, retrieved_context_hash,
             tool_schema_hash, output_schema_hash,
             selected_source_types, selected_process_stages, selected_entity_ids,
             included_gap_ids, included_contradiction_ids, schema_version
      FROM oracle_context_packs
      WHERE id = ${run.context_pack_id}
      LIMIT 1
    `);
    contextPack = ([...cpResult] as unknown as ContextPackDetail[])[0];
    if (contextPack?.blocks_json && Array.isArray(contextPack.blocks_json)) {
      blocks = contextPack.blocks_json as BlockJson[];
    }
  }

  const [batchesResult, cachesResult] = await Promise.all([
    db.execute(sql`
      SELECT id, status, batch_type, source_hash,
             validation_attempt_count, consecutive_quote_failure_count, created_at
      FROM extraction_batches
      WHERE model_run_id = ${id}
      ORDER BY created_at DESC
    `),
    db.execute(sql`
      SELECT id, provider, cache_kind, source_description,
             expected_reuse_count, actual_reuse_count, status,
             hard_expiration_at, deleted_at
      FROM provider_cached_content
      WHERE created_by_job_run_id IS NOT NULL
        AND (
          source_hash = ${run.stable_prefix_hash ?? ''}
          OR source_hash = ${run.dynamic_input_hash ?? ''}
        )
      ORDER BY created_at DESC
    `),
  ]);
  const batches = [...batchesResult] as unknown as ExtractionBatchRef[];
  const caches = [...cachesResult] as unknown as CacheRef[];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <Link href="/admin/ai/runs" className="text-xs text-muted-foreground hover:underline">
          ← back to runs
        </Link>
        <h1 className="text-2xl font-semibold">Model run</h1>
        <p className="text-sm font-mono text-muted-foreground">{run.model_run_id}</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run summary</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
            <Field label="Task type" value={run.task_type} />
            <Field
              label="Route"
              value={
                run.route_id ? (
                  <span className="font-mono">{run.route_id}</span>
                ) : (
                  <span className="italic text-muted-foreground">legacy (no route)</span>
                )
              }
            />
            <Field label="Provider" value={run.provider} />
            <Field label="Model ID" value={<span className="font-mono">{run.model}</span>} />
            <Field label="Prompt version" value={run.prompt_version ?? '—'} />
            <Field label="Latency" value={formatMs(run.latency_ms)} />
            <Field
              label="Status"
              value={
                run.success ? (
                  <span className="rounded bg-green-100 px-1.5 py-0.5 text-green-800">ok</span>
                ) : (
                  <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-800">failed</span>
                )
              }
            />
            <Field
              label="Created"
              value={new Date(run.run_created_at).toLocaleString()}
            />
            {run.fell_back_from_route_id && (
              <Field
                label="Fallback"
                value={
                  <span className="text-amber-700">
                    from <span className="font-mono">{run.fell_back_from_route_id}</span>
                  </span>
                }
              />
            )}
          </dl>
          {run.error && (
            <div className="mt-4 rounded border-l-4 border-red-500 bg-red-50 p-3 text-xs">
              <div className="font-semibold text-red-800">Error</div>
              <pre className="mt-1 whitespace-pre-wrap text-red-900">{run.error}</pre>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Usage breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
            <Field label="Input tokens" value={formatTokens(run.input_tokens)} />
            <Field label="Cached input" value={formatTokens(run.cached_input_tokens)} />
            <Field label="Cache write" value={formatTokens(run.cache_write_tokens)} />
            <Field label="Output tokens" value={formatTokens(run.output_tokens)} />
            <Field label="Reasoning tokens" value={formatTokens(run.reasoning_tokens)} />
            <Field label="Cache hit ratio" value={formatPct(run.cache_hit_ratio)} />
            <Field
              label="Provider request id"
              value={
                <span className="font-mono text-xs">{run.provider_request_id ?? '—'}</span>
              }
            />
            <Field label="Cost (USD)" value={run.cost_usd ?? '—'} />
          </dl>
        </CardContent>
      </Card>

      {contextPack && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Prompt plan</CardTitle>
            </CardHeader>
            <CardContent>
              {blocks.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No blocks_json recorded for this context pack.
                </p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="border-b text-left">
                    <tr>
                      <th className="py-2">#</th>
                      <th>Kind</th>
                      <th>Label</th>
                      <th className="text-right">Tokens</th>
                      <th>Cacheable</th>
                      <th>Reason</th>
                      <th className="text-right">Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blocks.map((b, i) => (
                      <tr key={b.id ?? i} className="border-b">
                        <td className="py-2">{i + 1}</td>
                        <td className="font-mono">{b.kind}</td>
                        <td>{b.label}</td>
                        <td className="text-right">{formatTokens(b.tokenEstimate)}</td>
                        <td>{b.cacheEligible ? 'yes' : 'no'}</td>
                        <td className="text-muted-foreground">{b.reasonIncluded}</td>
                        <td className="text-right font-mono text-[10px] text-muted-foreground">
                          {b.hash?.slice(0, 12) ?? '—'}…
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs md:grid-cols-3">
                <Field
                  label="stable_prefix_hash"
                  value={<HashCell value={run.stable_prefix_hash} />}
                />
                <Field
                  label="dynamic_input_hash"
                  value={<HashCell value={run.dynamic_input_hash} />}
                />
                <Field
                  label="semi_stable_context_hash"
                  value={<HashCell value={contextPack.semi_stable_context_hash} />}
                />
                <Field
                  label="retrieved_context_hash"
                  value={<HashCell value={contextPack.retrieved_context_hash} />}
                />
                <Field
                  label="tool_schema_hash"
                  value={<HashCell value={contextPack.tool_schema_hash} />}
                />
                <Field
                  label="output_schema_hash"
                  value={<HashCell value={contextPack.output_schema_hash} />}
                />
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Retrieval diagnostics</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm md:grid-cols-2">
                <Field
                  label="Retrieval plan ID"
                  value={
                    <span className="font-mono">{run.retrieval_plan_id ?? '—'}</span>
                  }
                />
                <Field
                  label="Selected domains"
                  value={<JsonList value={run.selected_domains} />}
                />
                <Field
                  label="Selected source types"
                  value={<JsonList value={contextPack.selected_source_types} />}
                />
                <Field
                  label="Selected process stages"
                  value={<JsonList value={contextPack.selected_process_stages} />}
                />
                <Field
                  label="Selected entity IDs"
                  value={<JsonList value={contextPack.selected_entity_ids} />}
                />
                <Field
                  label="Included message IDs"
                  value={<JsonCount value={run.included_message_ids} />}
                />
                <Field
                  label="Included document chunk IDs"
                  value={<JsonCount value={run.included_document_chunk_ids} />}
                />
                <Field
                  label="Included claim IDs"
                  value={<JsonCount value={run.included_claim_ids} />}
                />
                <Field
                  label="Included gap IDs"
                  value={<JsonCount value={contextPack.included_gap_ids} />}
                />
                <Field
                  label="Included contradiction IDs"
                  value={<JsonCount value={contextPack.included_contradiction_ids} />}
                />
              </dl>
            </CardContent>
          </Card>
        </>
      )}

      {batches.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Extraction batches from this run</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Batch</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th className="text-right">Attempts</th>
                  <th className="text-right">Consec. quote fails</th>
                  <th>Source hash</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.id} className="border-b">
                    <td className="py-2 font-mono">{b.id.slice(0, 12)}…</td>
                    <td>{b.batch_type}</td>
                    <td>
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs ${
                          b.status === 'validation_complete'
                            ? 'bg-green-100 text-green-800'
                            : b.status === 'failed_validation_loop'
                              ? 'bg-red-100 text-red-800'
                              : 'bg-muted'
                        }`}
                      >
                        {b.status}
                      </span>
                    </td>
                    <td className="text-right">{b.validation_attempt_count}</td>
                    <td className="text-right">{b.consecutive_quote_failure_count}</td>
                    <td className="font-mono text-muted-foreground">
                      {b.source_hash.slice(0, 12)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {caches.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Provider caches touched</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-xs">
              <thead className="border-b text-left">
                <tr>
                  <th className="py-2">Provider</th>
                  <th>Kind</th>
                  <th>Source</th>
                  <th className="text-right">Reuse</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {caches.map((c) => (
                  <tr key={c.id} className="border-b">
                    <td className="py-2">{c.provider}</td>
                    <td>{c.cache_kind}</td>
                    <td className="text-muted-foreground">{c.source_description ?? '—'}</td>
                    <td className="text-right">
                      {c.actual_reuse_count} / {c.expected_reuse_count}
                    </td>
                    <td>{c.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}

function HashCell({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="font-mono text-[10px]" title={value}>
      {value.slice(0, 16)}…
    </span>
  );
}

function JsonCount({ value }: { value: unknown }) {
  if (!Array.isArray(value)) return <span className="text-muted-foreground">—</span>;
  return <span>{value.length} ID{value.length === 1 ? '' : 's'}</span>;
}

function JsonList({ value }: { value: unknown }) {
  if (!Array.isArray(value) || value.length === 0)
    return <span className="text-muted-foreground">—</span>;
  return (
    <span className="font-mono text-xs">
      {value.map((v) => String(v)).join(', ')}
    </span>
  );
}
