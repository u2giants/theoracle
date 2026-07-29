export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { EVAL_STAGES, type EvalGateStatus, type EvalStage } from '@oracle/ai/eval-results';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { filterEvalResults, loadEvalResults } from '@/lib/eval-results';
import { formatNYDateTime } from '@/lib/time';

type Params = {
  stage?: string;
  commit?: string;
  status?: string;
  from?: string;
  to?: string;
};

function validStage(value: string | undefined): EvalStage | undefined {
  return EVAL_STAGES.includes(value as EvalStage) ? value as EvalStage : undefined;
}

function validStatus(value: string | undefined): EvalGateStatus | undefined {
  return value === 'PASS' || value === 'FAIL' ? value : undefined;
}

export default async function AdminAIEvalsPage({
  searchParams,
}: {
  searchParams: Promise<Params>;
}) {
  const params = await searchParams;
  const result = loadEvalResults();
  const stage = validStage(params.stage);
  const status = validStatus(params.status);
  const commit = params.commit?.trim().toLowerCase() ?? '';
  const runs = result.ok ? filterEvalResults(result.runs, params) : [];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Eval results</h1>
        <p className="text-sm text-muted-foreground">
          Read-only release gates saved by CLI eval runs. No prompts, source text, or credentials
          are stored here.
        </p>
      </header>

      <Card>
        <CardHeader><CardTitle className="text-base">Filters</CardTitle></CardHeader>
        <CardContent>
          <form className="grid gap-3 text-sm md:grid-cols-5">
            <label className="space-y-1">Stage
              <select name="stage" defaultValue={stage ?? ''} className="block w-full rounded border bg-background p-2">
                <option value="">All stages</option>
                {EVAL_STAGES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="space-y-1">Commit
              <input name="commit" defaultValue={commit} placeholder="SHA prefix" className="block w-full rounded border bg-background p-2" />
            </label>
            <label className="space-y-1">Result
              <select name="status" defaultValue={status ?? ''} className="block w-full rounded border bg-background p-2">
                <option value="">Pass or fail</option>
                <option value="PASS">Pass</option>
                <option value="FAIL">Fail</option>
              </select>
            </label>
            <label className="space-y-1">From (UTC)
              <input type="date" name="from" defaultValue={params.from ?? ''} className="block w-full rounded border bg-background p-2" />
            </label>
            <label className="space-y-1">To (UTC)
              <input type="date" name="to" defaultValue={params.to ?? ''} className="block w-full rounded border bg-background p-2" />
            </label>
            <div className="flex gap-2 md:col-span-5">
              <button className="rounded bg-primary px-3 py-2 text-primary-foreground">Apply filters</button>
              <Link href="/admin/ai/evals" className="rounded border px-3 py-2">Clear</Link>
            </div>
          </form>
        </CardContent>
      </Card>

      {!result.ok ? (
        <Card className="border-red-300"><CardContent className="py-6 text-sm text-red-700">{result.error}</CardContent></Card>
      ) : runs.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          {result.runs.length === 0
            ? 'No saved eval results yet. Run pnpm --filter @oracle/ai eval:extraction to create the first safe summary.'
            : 'No eval runs match these filters.'}
        </CardContent></Card>
      ) : (
        <Card>
          <CardHeader><CardTitle className="text-base">{runs.length} saved run{runs.length === 1 ? '' : 's'}</CardTitle></CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-xs">
              <caption className="sr-only">Saved CLI evaluation runs and release gate results</caption>
              <thead className="border-b text-left"><tr>
                <th scope="col" className="py-2">Completed</th><th scope="col">Stage</th>
                <th scope="col">Route / prompt</th><th scope="col">Commit / fixtures</th>
                <th scope="col" className="text-right">Gate metrics</th><th scope="col">Result</th>
              </tr></thead>
              <tbody>{runs.map((run) => {
                const passed = run.stages.reduce((sum, item) => sum + item.passedCount, 0);
                const failed = run.stages.reduce((sum, item) => sum + item.failedCount, 0);
                return <tr key={run.runId} className="border-b">
                  <td className="py-2"><Link href={`/admin/ai/evals/${encodeURIComponent(run.runId)}`} className="font-medium hover:underline">{formatNYDateTime(run.completedAt)}</Link></td>
                  <td>{run.stages.map((item) => item.stage).join(', ')}</td>
                  <td><div className="font-mono">{run.routeId}</div><div className="font-mono text-muted-foreground">{run.modelId ?? 'model not recorded'}</div><div className="text-muted-foreground">prompt {run.promptVersion}</div></td>
                  <td><div className="font-mono">{run.commitSha.slice(0, 7)}</div><div className="font-mono text-muted-foreground">{run.fixtureVersion.slice(0, 8)}</div></td>
                  <td className="text-right"><div>{passed} passed · {failed} failed</div><div className="text-muted-foreground">
                    {run.stages[0]?.metrics.quoteValidity != null ? `${(run.stages[0].metrics.quoteValidity * 100).toFixed(1)}% quotes` : 'No quote metric'}
                  </div><div className="text-muted-foreground">{run.execution.latencyMs == null ? 'latency not measured' : `${run.execution.latencyMs} ms`}{run.execution.inputTokens == null ? '' : ` · ${run.execution.inputTokens} input tokens`}{run.execution.costUsd == null ? '' : ` · $${run.execution.costUsd.toFixed(4)}`}</div></td>
                  <td><span className={run.gateStatus === 'PASS' ? 'text-green-700' : 'text-red-700'}>{run.gateStatus}</span></td>
                </tr>;
              })}</tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
