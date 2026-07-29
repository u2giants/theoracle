import {
  EVAL_STAGES,
  parseSafeEvalRunSummary,
  type EvalGateStatus,
  type EvalStage,
  type SafeEvalRunSummary,
} from '@oracle/ai/eval-results';
import publishedJson from '../../../packages/ai/evals/published/index.json';

type LoadResult =
  | { ok: true; runs: SafeEvalRunSummary[] }
  | { ok: false; error: string; runs: [] };

export function loadEvalResults(): LoadResult {
  try {
    const published = publishedJson as unknown as { schemaVersion?: unknown; runs?: unknown };
    if (!published || published.schemaVersion !== 1 || !Array.isArray(published.runs)) {
      throw new Error('The saved eval index has an unsupported format.');
    }
    const ids = new Set<string>();
    const runs = published.runs.map((value) => {
      const run = parseSafeEvalRunSummary(value);
      if (ids.has(run.runId)) throw new Error(`Duplicate eval run: ${run.runId}`);
      ids.add(run.runId);
      return run;
    });
    runs.sort((a, b) => Date.parse(b.completedAt) - Date.parse(a.completedAt));
    return { ok: true, runs };
  } catch (error) {
    console.error('[eval-results] Stored summary validation failed:', error);
    return {
      ok: false,
      error: 'Saved eval results could not be read. Run the CLI eval again and check the safe summary.',
      runs: [],
    };
  }
}

export function findEvalResult(runId: string): LoadResult & { run?: SafeEvalRunSummary } {
  const result = loadEvalResults();
  if (!result.ok) return result;
  return { ...result, run: result.runs.find((run) => run.runId === runId) };
}

export function githubArtifactUrl(_run: SafeEvalRunSummary, path: string): string {
  return `https://github.com/u2giants/theoracle/blob/${_run.commitSha}/${path}`;
}

export type EvalResultFilters = {
  stage?: string;
  commit?: string;
  status?: string;
  from?: string;
  to?: string;
};

export function filterEvalResults(
  runs: SafeEvalRunSummary[],
  filters: EvalResultFilters,
): SafeEvalRunSummary[] {
  const stage = EVAL_STAGES.includes(filters.stage as EvalStage)
    ? filters.stage as EvalStage
    : undefined;
  const status: EvalGateStatus | undefined =
    filters.status === 'PASS' || filters.status === 'FAIL' ? filters.status : undefined;
  const commit = filters.commit?.trim().toLowerCase() ?? '';
  const from = dateBoundary(filters.from);
  const to = dateBoundary(filters.to, true);
  return runs.filter((run) => {
    const completed = Date.parse(run.completedAt);
    return (
      (!stage || run.stages.some((item) => item.stage === stage)) &&
      (!status || run.gateStatus === status) &&
      (!commit || run.commitSha.toLowerCase().startsWith(commit)) &&
      (from == null || completed >= from) &&
      (to == null || completed <= to)
    );
  });
}

function dateBoundary(value: string | undefined, endOfDay = false): number | undefined {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = Date.parse(`${value}T${endOfDay ? '23:59:59.999' : '00:00:00.000'}Z`);
  return Number.isFinite(parsed) ? parsed : undefined;
}
