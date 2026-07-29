export const EVAL_STAGES = [
  'extraction',
  'retrieval',
  'synthesis',
  'validation',
  'segmentation',
  'cache',
] as const;

export type EvalStage = (typeof EVAL_STAGES)[number];
export type EvalGateStatus = 'PASS' | 'FAIL';

export interface SafeEvalArtifact {
  label: string;
  path: string;
}

export interface SafeEvalStageSummary {
  stage: EvalStage;
  gateStatus: EvalGateStatus;
  fixtureCount: number;
  passedCount: number;
  failedCount: number;
  metrics: Record<string, number | null>;
}

export interface SafeEvalRunSummary {
  schemaVersion: 1;
  runId: string;
  startedAt: string;
  completedAt: string;
  commitSha: string;
  fixtureVersion: string;
  promptVersion: string;
  mode: 'mock' | 'live';
  routeId: string;
  modelId: string | null;
  gateStatus: EvalGateStatus;
  stages: SafeEvalStageSummary[];
  execution: {
    latencyMs: number | null;
    inputTokens: number | null;
    outputTokens: number | null;
    costUsd: number | null;
  };
  artifacts: SafeEvalArtifact[];
}

const RUN_ID = /^[a-z0-9][a-z0-9._-]{0,119}$/i;
const COMMIT_SHA = /^[a-f0-9]{7,40}$/i;
const SAFE_ARTIFACT_PATH = /^packages\/ai\/evals\/published\/[a-z0-9._-]+\.json$/i;

export function parseSafeEvalRunSummary(value: unknown): SafeEvalRunSummary {
  if (!value || typeof value !== 'object') throw new Error('Eval summary must be an object.');
  const run = value as Partial<SafeEvalRunSummary>;
  if (run.schemaVersion !== 1) throw new Error('Unsupported eval summary version.');
  if (typeof run.runId !== 'string' || !RUN_ID.test(run.runId)) throw new Error('Invalid eval run ID.');
  if (typeof run.commitSha !== 'string' || !COMMIT_SHA.test(run.commitSha)) {
    throw new Error('Invalid eval commit SHA.');
  }
  if (typeof run.fixtureVersion !== 'string' || !/^[a-f0-9]{64}$/i.test(run.fixtureVersion)) {
    throw new Error('Invalid eval fixture version.');
  }
  if (
    typeof run.promptVersion !== 'string' ||
    run.promptVersion.length === 0 ||
    run.promptVersion.length > 100
  ) {
    throw new Error('Invalid eval prompt version.');
  }
  if (run.mode !== 'mock' && run.mode !== 'live') throw new Error('Invalid eval mode.');
  if (run.gateStatus !== 'PASS' && run.gateStatus !== 'FAIL') {
    throw new Error('Invalid eval gate status.');
  }
  if (typeof run.routeId !== 'string' || run.routeId.length === 0 || run.routeId.length > 200) {
    throw new Error('Invalid eval route.');
  }
  if (
    run.modelId !== null &&
    (typeof run.modelId !== 'string' || run.modelId.length === 0 || run.modelId.length > 200)
  ) {
    throw new Error('Invalid eval model.');
  }
  if (
    typeof run.startedAt !== 'string' ||
    !Number.isFinite(Date.parse(run.startedAt)) ||
    typeof run.completedAt !== 'string' ||
    !Number.isFinite(Date.parse(run.completedAt))
  ) {
    throw new Error('Invalid eval timestamps.');
  }
  if (Date.parse(run.startedAt) > Date.parse(run.completedAt)) {
    throw new Error('Eval start time is after completion.');
  }
  const stages: SafeEvalStageSummary[] = [];
  if (!Array.isArray(run.stages) || run.stages.length === 0) {
    throw new Error('Eval summary has no stages.');
  }
  for (const stage of run.stages) {
    if (!EVAL_STAGES.includes(stage.stage) || !['PASS', 'FAIL'].includes(stage.gateStatus)) {
      throw new Error('Invalid eval stage.');
    }
    for (const count of [stage.fixtureCount, stage.passedCount, stage.failedCount]) {
      if (!Number.isSafeInteger(count) || count < 0) throw new Error('Invalid eval count.');
    }
    if (stage.passedCount + stage.failedCount > stage.fixtureCount) {
      throw new Error('Eval stage counts exceed fixture count.');
    }
    if (!stage.metrics || typeof stage.metrics !== 'object' || Array.isArray(stage.metrics)) {
      throw new Error('Invalid eval metrics.');
    }
    const metrics: Record<string, number | null> = {};
    for (const metric of Object.values(stage.metrics)) {
      if (metric !== null && (typeof metric !== 'number' || !Number.isFinite(metric))) {
        throw new Error('Invalid eval metric.');
      }
    }
    for (const [name, metric] of Object.entries(stage.metrics)) {
      if (!/^[a-z][a-zA-Z0-9]{0,79}$/.test(name)) throw new Error('Invalid eval metric name.');
      metrics[name] = metric;
    }
    stages.push({
      stage: stage.stage,
      gateStatus: stage.gateStatus,
      fixtureCount: stage.fixtureCount,
      passedCount: stage.passedCount,
      failedCount: stage.failedCount,
      metrics,
    });
  }
  if (!run.execution || typeof run.execution !== 'object' || Array.isArray(run.execution)) {
    throw new Error('Invalid eval execution metrics.');
  }
  const execution = {
    latencyMs: run.execution.latencyMs,
    inputTokens: run.execution.inputTokens,
    outputTokens: run.execution.outputTokens,
    costUsd: run.execution.costUsd,
  };
  for (const metric of Object.values(execution)) {
    if (metric !== null && (typeof metric !== 'number' || !Number.isFinite(metric) || metric < 0)) {
      throw new Error('Invalid eval execution metric.');
    }
  }
  if (!Array.isArray(run.artifacts)) throw new Error('Invalid eval artifacts.');
  const artifacts: SafeEvalArtifact[] = [];
  for (const artifact of run.artifacts) {
    if (
      typeof artifact.label !== 'string' ||
      artifact.label.length === 0 ||
      artifact.label.length > 80 ||
      typeof artifact.path !== 'string' ||
      !SAFE_ARTIFACT_PATH.test(artifact.path)
    ) {
      throw new Error('Unsafe eval artifact link.');
    }
    artifacts.push({ label: artifact.label, path: artifact.path });
  }
  return {
    schemaVersion: 1,
    runId: run.runId,
    startedAt: run.startedAt,
    completedAt: run.completedAt,
    commitSha: run.commitSha,
    fixtureVersion: run.fixtureVersion,
    promptVersion: run.promptVersion,
    mode: run.mode,
    routeId: run.routeId,
    modelId: run.modelId,
    gateStatus: run.gateStatus,
    stages,
    execution,
    artifacts,
  };
}
