import { eq, inArray, sql } from 'drizzle-orm';
import {
  documentChunks,
  settings,
  sourceGroupItems,
  sourceGroups,
  sourceOutlines,
  type OracleDb,
} from '@oracle/db';
import { EXTRACTION_LENSES, type SourceOutlineOutput } from '@oracle/ai';

export type ExtractionLens = (typeof EXTRACTION_LENSES)[number];

export type LensBudget = {
  enabled: boolean;
  maxLensesPerDocument: number;
  maxGroupsPerDocument: number;
  maxModelCallsPerDocument: number;
  maxEstimatedInputTokens: number;
};

export type LensDispatchPlan = {
  selected: Array<{
    sourceGroupId: string;
    groupTitle: string;
    lens: ExtractionLens;
    estimatedInputTokens: number;
  }>;
  skipped: Array<{
    sourceGroupId?: string;
    groupTitle?: string;
    lens?: string;
    reason: string;
  }>;
  budget: LensBudget;
};

const LENS_PRIORITY: ExtractionLens[] = [
  'handoffs',
  'exceptions_and_workarounds',
  'dependencies_and_sequence',
  'contradictions_and_tensions',
  'systems_and_data_entry',
  'ownership_and_roles',
  'definitions_and_acronyms',
  'customer_or_licensor_risk',
];

function settingToBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value === 'true' || value === '1';
  return fallback;
}

function settingToInt(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? Math.floor(parsed) : fallback;
}

function isExtractionLens(value: unknown): value is ExtractionLens {
  return typeof value === 'string' && (EXTRACTION_LENSES as readonly string[]).includes(value);
}

function priority(lens: ExtractionLens): number {
  const index = LENS_PRIORITY.indexOf(lens);
  return index >= 0 ? index : LENS_PRIORITY.length;
}

export async function loadLensBudget(db: OracleDb): Promise<LensBudget> {
  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(
      inArray(settings.key, [
        'macro_lenses_enabled',
        'macro_max_lenses_per_document',
        'macro_max_lens_groups_per_document',
        'macro_max_lens_model_calls_per_document',
        'macro_max_lens_estimated_input_tokens',
      ]),
    );
  const values = new Map(rows.map((row) => [row.key, row.value]));
  return {
    enabled: settingToBoolean(values.get('macro_lenses_enabled'), true),
    maxLensesPerDocument: Math.max(0, settingToInt(values.get('macro_max_lenses_per_document'), 4)),
    maxGroupsPerDocument: Math.max(
      0,
      settingToInt(values.get('macro_max_lens_groups_per_document'), 8),
    ),
    maxModelCallsPerDocument: Math.max(
      0,
      settingToInt(values.get('macro_max_lens_model_calls_per_document'), 4),
    ),
    maxEstimatedInputTokens: Math.max(
      0,
      settingToInt(values.get('macro_max_lens_estimated_input_tokens'), 32_000),
    ),
  };
}

export async function buildLensDispatchPlan(
  db: OracleDb,
  sourceOutlineId: string,
): Promise<LensDispatchPlan> {
  const budget = await loadLensBudget(db);
  const skipped: LensDispatchPlan['skipped'] = [];
  if (!budget.enabled)
    return { selected: [], skipped: [{ reason: 'macro_lenses_disabled' }], budget };
  if (budget.maxLensesPerDocument === 0 || budget.maxModelCallsPerDocument === 0) {
    return { selected: [], skipped: [{ reason: 'macro_lens_budget_zero' }], budget };
  }

  const [outline] = await db
    .select({
      id: sourceOutlines.id,
      outlineJson: sourceOutlines.outlineJson,
      summary: sourceOutlines.summary,
    })
    .from(sourceOutlines)
    .where(eq(sourceOutlines.id, sourceOutlineId))
    .limit(1);
  if (!outline) return { selected: [], skipped: [{ reason: 'source_outline_not_found' }], budget };

  const outlineJson = outline.outlineJson as Partial<SourceOutlineOutput>;
  const outlineLenses = (outlineJson.recommendedLenses ?? []).filter(isExtractionLens);
  const groups = await db
    .select({
      id: sourceGroups.id,
      title: sourceGroups.title,
      groupType: sourceGroups.groupType,
      metadataJson: sourceGroups.metadataJson,
      sortOrder: sourceGroups.sortOrder,
      textChars: sql<number>`COALESCE(SUM(length(${documentChunks.rawText})), 0)`,
    })
    .from(sourceGroups)
    .leftJoin(sourceGroupItems, eq(sourceGroupItems.sourceGroupId, sourceGroups.id))
    .leftJoin(documentChunks, eq(documentChunks.id, sourceGroupItems.documentChunkId))
    .where(eq(sourceGroups.sourceOutlineId, sourceOutlineId))
    .groupBy(sourceGroups.id)
    .orderBy(sourceGroups.sortOrder);

  // COVERAGE-FIRST budgeting (2026-07-03). The old plan (a) hard-dropped groups
  // beyond maxGroupsPerDocument — which silently deleted the *terminal* workflow
  // stages (SKU creation, production, shipment) because they sort last — and (b)
  // sorted candidates lens-major, so the whole budget was spent running ONE lens
  // (handoffs) on the first few groups. Both together meant the endgame of a
  // swimlane diagram got zero lens coverage. See fix_enhancement.md §5 Bugs A/B/F.
  //
  // New model: every source group is a "round". Round 0 gives EVERY group its
  // single highest-priority lens before any group gets a second lens (round 1),
  // etc. Selection then walks rounds in order, so breadth-across-the-workflow
  // wins over depth-on-one-stage, and terminal stages are never dropped by sort
  // position. Cost stays bounded by maxModelCallsPerDocument and the token ceiling.
  const perGroup = groups.map((group) => {
    const metadata = group.metadataJson as { recommendedLenses?: unknown[] } | null;
    const groupLenses = (metadata?.recommendedLenses ?? []).filter(isExtractionLens);
    const lenses = [...new Set([...groupLenses, ...outlineLenses])].sort(
      (a, b) => priority(a) - priority(b),
    );
    // maxLensesPerDocument is a per-GROUP depth cap (its name is legacy; see the
    // note in loadLensBudget). It bounds how many lenses one stage can consume.
    const kept = lenses.slice(0, budget.maxLensesPerDocument);
    for (const lens of lenses.slice(budget.maxLensesPerDocument)) {
      skipped.push({
        sourceGroupId: group.id,
        groupTitle: group.title,
        lens,
        reason: `group_lens_depth_exceeds_${budget.maxLensesPerDocument}`,
      });
    }
    return {
      group,
      lenses: kept,
      estimatedInputTokens: Math.max(1, Math.ceil((Number(group.textChars) || 0) / 4) + 1500),
    };
  });

  const maxRounds = Math.max(0, ...perGroup.map((g) => g.lenses.length));
  const candidates: Array<{
    sourceGroupId: string;
    groupTitle: string;
    groupSort: number;
    lens: ExtractionLens;
    estimatedInputTokens: number;
    round: number;
  }> = [];
  // Round-major, then group sort order: [g0.lens0, g1.lens0, … , g0.lens1, …].
  for (let round = 0; round < maxRounds; round += 1) {
    for (const g of perGroup) {
      const lens = g.lenses[round];
      if (!lens) continue;
      candidates.push({
        sourceGroupId: g.group.id,
        groupTitle: g.group.title,
        groupSort: g.group.sortOrder ?? 0,
        lens,
        estimatedInputTokens: g.estimatedInputTokens,
        round,
      });
    }
  }

  const selected: LensDispatchPlan['selected'] = [];
  let tokenTotal = 0;
  const callLimit = budget.maxModelCallsPerDocument;
  for (const candidate of candidates) {
    if (selected.length >= callLimit) {
      skipped.push({ ...candidate, reason: `model_call_count_exceeds_${callLimit}` });
      continue;
    }
    if (tokenTotal + candidate.estimatedInputTokens > budget.maxEstimatedInputTokens) {
      skipped.push({
        ...candidate,
        reason: `estimated_input_tokens_exceed_${budget.maxEstimatedInputTokens}`,
      });
      continue;
    }
    selected.push({
      sourceGroupId: candidate.sourceGroupId,
      groupTitle: candidate.groupTitle,
      lens: candidate.lens,
      estimatedInputTokens: candidate.estimatedInputTokens,
    });
    tokenTotal += candidate.estimatedInputTokens;
  }

  return { selected, skipped, budget };
}

export async function documentHasCompletedLensBatch(args: {
  db: OracleDb;
  sourceHash: string;
}): Promise<boolean> {
  // Must include the TERMINAL status 'complete' (document-lens-extraction.ts
  // writes 'complete' as the final batch state). Omitting it made a fully
  // finished lens batch invisible to this guard, so a re-run re-extracted and
  // re-promoted duplicate lens claims (fix_enhancement.md §5 Bug C).
  const rows = await args.db.execute<{ id: string }>(sql`
    SELECT id
    FROM extraction_batches
    WHERE batch_type = 'document_lens_group'
      AND source_hash = ${args.sourceHash}
      AND status IN ('pending_model', 'model_complete', 'validation_complete', 'complete')
    LIMIT 1
  `);
  return [...rows].length > 0;
}
