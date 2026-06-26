import type { OracleDb } from '@oracle/db';
import { modelRunAttempts } from '@oracle/db/schema';
import type { OracleRunRouteMetadata } from '../client/types';
import { AllCandidatesFailedError, type ModelSlot } from './errors';

export interface LogModelAttemptsArgs {
  db: OracleDb;
  metadata: OracleRunRouteMetadata;
  taskType: string;
  slot: ModelSlot;
  contextPackId?: string | null;
  modelRunId?: string | null;
}

export async function logModelRunAttempts({
  db,
  metadata,
  taskType,
  slot,
  contextPackId,
  modelRunId,
}: LogModelAttemptsArgs): Promise<void> {
  const attempts = metadata.attemptedRoutes ?? [];
  if (attempts.length === 0) return;
  await db.insert(modelRunAttempts).values(
    attempts.map((attempt, index) => ({
      modelRunId: modelRunId ?? null,
      contextPackId: contextPackId ?? null,
      taskType,
      slot,
      attemptIndex: index,
      routeId: attempt.routeId,
      provider: attempt.provider,
      modelId: attempt.modelId,
      isPrimary: index === 0,
      status: attempt.success ? 'success' : 'failed',
      error: attempt.error ?? null,
    })),
  );
}

export async function logAllCandidatesFailedAttempts(args: {
  db: OracleDb;
  error: unknown;
  taskType: string;
  slot: ModelSlot;
  contextPackId?: string | null;
}): Promise<void> {
  if (!(args.error instanceof AllCandidatesFailedError)) return;
  await args.db.insert(modelRunAttempts).values(
    args.error.attempts.map((attempt, index) => ({
      modelRunId: null,
      contextPackId: args.contextPackId ?? null,
      taskType: args.taskType,
      slot: args.slot,
      attemptIndex: index,
      routeId: attempt.routeId,
      provider: attempt.provider,
      modelId: attempt.modelId,
      isPrimary: index === 0,
      status: 'failed',
      error: attempt.error,
    })),
  );
}
