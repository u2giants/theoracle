import { tasks } from '@trigger.dev/sdk/v3';
import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';
import { buildLensDispatchPlan } from './document-lens-budget';
import { markMacroDegraded, markMacroPending } from './macro-health';

type MacroAutoBudget = {
  enabled: boolean;
  maxOutlineGroups: number;
};

type MacroFollowupResult = {
  triggered: boolean;
  reason?: string;
};

function settingToBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value === 'true' || value === '1';
  return fallback;
}

function settingToInt(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? Math.floor(parsed) : fallback;
}

export async function loadMacroAutoBudget(db: OracleDb): Promise<MacroAutoBudget> {
  const rows = await db.execute(
    sql`SELECT key, value FROM settings WHERE key IN ('macro_auto_followups_enabled', 'macro_auto_max_outline_groups')`,
  );
  const map = new Map(
    ([...rows] as Array<{ key: string; value: unknown }>).map((row) => [row.key, row.value]),
  );
  return {
    enabled: settingToBoolean(map.get('macro_auto_followups_enabled'), true),
    maxOutlineGroups: Math.max(1, settingToInt(map.get('macro_auto_max_outline_groups'), 12)),
  };
}

async function claimMacroFollowupDispatch(args: {
  db: OracleDb;
  outlineId: string;
  reason: string;
}): Promise<boolean> {
  const rows = await args.db.execute<{ id: string }>(sql`
    UPDATE source_outlines
    SET budget_json = COALESCE(budget_json, '{}'::jsonb)
      || jsonb_build_object(
        'macroFollowupsDispatchedAt', now(),
        'macroFollowupsDispatchReason', ${args.reason}
      ),
      updated_at = now()
    WHERE id = ${args.outlineId}::uuid
      AND NOT (COALESCE(budget_json, '{}'::jsonb) ? 'macroFollowupsDispatchedAt')
    RETURNING id
  `);
  return [...rows].length > 0;
}

export async function triggerMacroFollowupsOnce(args: {
  db: OracleDb;
  documentId: string;
  outlineId: string;
  groupCount: number;
  reason: string;
}): Promise<MacroFollowupResult> {
  const budget = await loadMacroAutoBudget(args.db);
  if (!budget.enabled) return { triggered: false, reason: 'macro_auto_followups_disabled' };
  if (args.groupCount > budget.maxOutlineGroups) {
    return {
      triggered: false,
      reason: `outline_group_count_${args.groupCount}_exceeds_${budget.maxOutlineGroups}`,
    };
  }

  const claimed = await claimMacroFollowupDispatch({
    db: args.db,
    outlineId: args.outlineId,
    reason: args.reason,
  });
  if (!claimed) return { triggered: false, reason: 'macro_followups_already_dispatched' };

  await markMacroPending(args.db, args.documentId);

  try {
    await tasks.trigger('macro-relationship-extraction', {
      documentId: args.documentId,
      sourceOutlineId: args.outlineId,
      relationshipScope: 'cross_source',
    });
    return { triggered: true };
  } catch (err) {
    await markMacroDegraded(args.db, args.documentId);
    console.warn('[macro-followups] failed to trigger macro relationship extraction', err);
    return { triggered: false, reason: 'macro_relationship_trigger_failed' };
  }
}

export async function maybeTriggerMacroFollowupsAfterLensCompletion(args: {
  db: OracleDb;
  documentId: string;
  outlineId: string;
}): Promise<MacroFollowupResult> {
  const groupRows = await args.db.execute<{ count: number }>(sql`
    SELECT COUNT(*)::int AS count
    FROM source_groups
    WHERE source_outline_id = ${args.outlineId}::uuid
  `);
  const groupCount = Number([...groupRows][0]?.count ?? 0);
  const plan = await buildLensDispatchPlan(args.db, args.outlineId);
  const planned = plan.selected.length;
  if (planned === 0) {
    return triggerMacroFollowupsOnce({
      db: args.db,
      documentId: args.documentId,
      outlineId: args.outlineId,
      groupCount,
      reason: 'no_lens_jobs_selected',
    });
  }

  const rows = await args.db.execute<{ completed: number }>(sql`
    SELECT COUNT(DISTINCT (input_json->>'sourceGroupId') || ':' || (input_json->>'lens'))::int AS completed
    FROM job_runs
    WHERE job_type = 'document-lens-extraction'
      AND status = 'complete'
      AND input_json->>'documentId' = ${args.documentId}
      AND input_json->>'sourceOutlineId' = ${args.outlineId}
  `);
  const completed = Number([...rows][0]?.completed ?? 0);
  if (completed < planned) {
    return {
      triggered: false,
      reason: `lens_jobs_complete_${completed}_of_${planned}`,
    };
  }

  return triggerMacroFollowupsOnce({
    db: args.db,
    documentId: args.documentId,
    outlineId: args.outlineId,
    groupCount,
    reason: 'lens_fanout_complete',
  });
}
