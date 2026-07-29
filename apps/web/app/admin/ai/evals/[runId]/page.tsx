export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { findEvalResult, githubArtifactUrl } from '@/lib/eval-results';
import { formatNYDateTime } from '@/lib/time';

function metricLabel(value: string): string {
  return value.replace(/([A-Z])/g, ' $1').replace(/^./, (letter) => letter.toUpperCase());
}

function metricValue(name: string, value: number | null): string {
  if (value == null) return 'Not measured';
  if (/precision|recall|f1|validity|rate/i.test(name)) return `${(value * 100).toFixed(1)}%`;
  return String(value);
}

export default async function EvalRunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const result = findEvalResult(runId);
  if (!result.ok) {
    return <Card className="border-red-300"><CardContent className="py-6 text-sm text-red-700">{result.error}</CardContent></Card>;
  }
  if (!result.run) notFound();
  const run = result.run;

  return <div className="space-y-6">
    <header className="space-y-2">
      <Link href="/admin/ai/evals" className="text-sm text-muted-foreground hover:underline">← Eval results</Link>
      <h1 className="text-2xl font-semibold">Eval run detail</h1>
      <p className="font-mono text-xs text-muted-foreground">{run.runId}</p>
    </header>
    <Card><CardHeader><CardTitle className="text-base">Release link</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-sm md:grid-cols-2">
        <div><div className="text-xs text-muted-foreground">Result</div><div className={run.gateStatus === 'PASS' ? 'font-semibold text-green-700' : 'font-semibold text-red-700'}>{run.gateStatus}</div></div>
        <div><div className="text-xs text-muted-foreground">Completed</div><div>{formatNYDateTime(run.completedAt)}</div></div>
        <div><div className="text-xs text-muted-foreground">Exact commit</div><div className="break-all font-mono">{run.commitSha}</div></div>
        <div><div className="text-xs text-muted-foreground">Fixture version</div><div className="break-all font-mono">{run.fixtureVersion}</div></div>
        <div><div className="text-xs text-muted-foreground">Prompt version</div><div className="font-mono">{run.promptVersion}</div></div>
        <div><div className="text-xs text-muted-foreground">Mode</div><div>{run.mode}</div></div>
        <div><div className="text-xs text-muted-foreground">Route</div><div className="break-all font-mono">{run.routeId}</div></div>
        <div><div className="text-xs text-muted-foreground">Model</div><div className="break-all font-mono">{run.modelId ?? 'Not recorded'}</div></div>
        <div><div className="text-xs text-muted-foreground">Latency</div><div>{run.execution.latencyMs == null ? 'Not measured' : `${run.execution.latencyMs} ms`}</div></div>
        <div><div className="text-xs text-muted-foreground">Tokens / cost</div><div>{run.execution.inputTokens == null ? 'Not measured' : `${run.execution.inputTokens} in · ${run.execution.outputTokens ?? 0} out`}{run.execution.costUsd == null ? '' : ` · $${run.execution.costUsd.toFixed(4)}`}</div></div>
      </CardContent>
    </Card>
    {run.stages.map((stage) => <Card key={stage.stage}>
      <CardHeader><CardTitle className="flex items-center justify-between text-base"><span className="capitalize">{stage.stage}</span><span className={stage.gateStatus === 'PASS' ? 'text-green-700' : 'text-red-700'}>{stage.gateStatus}</span></CardTitle></CardHeader>
      <CardContent>
        <div className="mb-4 grid grid-cols-3 gap-3 text-sm"><div>Fixtures: {stage.fixtureCount}</div><div>Passed: {stage.passedCount}</div><div>Failed: {stage.failedCount}</div></div>
        <dl className="grid gap-2 text-sm md:grid-cols-2">{Object.entries(stage.metrics).map(([name, value]) =>
          <div key={name} className="flex justify-between gap-4 border-b py-1"><dt className="text-muted-foreground">{metricLabel(name)}</dt><dd className="font-mono">{metricValue(name, value)}</dd></div>
        )}</dl>
      </CardContent>
    </Card>)}
    <Card><CardHeader><CardTitle className="text-base">Safe artifacts</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-sm">{run.artifacts.length === 0
        ? <p className="text-muted-foreground">No safe artifacts were published.</p>
        : run.artifacts.map((artifact) => <a key={artifact.path} href={githubArtifactUrl(run, artifact.path)} target="_blank" rel="noopener noreferrer" className="block hover:underline">{artifact.label} ↗</a>)}
        <p className="text-xs text-muted-foreground">Raw CLI files stay local and are not linked from this dashboard.</p>
      </CardContent>
    </Card>
  </div>;
}
