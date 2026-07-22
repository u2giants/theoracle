import { and, eq, inArray, sql } from 'drizzle-orm';
import { claims, gaps, type OracleDb } from '@oracle/db';
import type { ActiveWorkflowMapContext } from './source-workflow-read';
import {
  modelCoverageGapId,
  reconcileMapPrimaryClaims,
  type MapCoverageReconciliation,
} from './map-coverage';

export const MODEL_COVERAGE_GAP_TYPE = 'model_coverage';

export async function reconcileAndWriteMapCoverageGaps(args: {
  db: OracleDb;
  sourceType: 'document';
  sourceId: string;
  activeMap: ActiveWorkflowMapContext;
}): Promise<MapCoverageReconciliation> {
  const claimRows = await args.db
    .select({ mapElementRef: claims.mapElementRef })
    .from(claims)
    .where(
      and(
        sql`${claims.mapElementRef} LIKE ${`${args.activeMap.mapId}:%`}`,
        sql`${claims.status} NOT IN ('rejected', 'superseded')`,
      ),
    );
  const reconciliation = reconcileMapPrimaryClaims({
    mapId: args.activeMap.mapId,
    map: args.activeMap.map,
    claimMapElementRefs: claimRows
      .map((row) => row.mapElementRef)
      .filter((ref): ref is string => Boolean(ref)),
  });

  const idsByRef = new Map(
    reconciliation.primaryRefs.map((ref) => [
      ref.ref,
      modelCoverageGapId({
        sourceType: args.sourceType,
        sourceId: args.sourceId,
        mapId: args.activeMap.mapId,
        mapElementRef: ref.ref,
      }),
    ]),
  );
  const coveredIds = reconciliation.coveredRefs.map((ref) => idsByRef.get(ref.ref)!);
  if (coveredIds.length > 0) {
    await args.db
      .update(gaps)
      .set({ status: 'stale', updatedAt: new Date() })
      .where(
        and(
          eq(gaps.gapType, MODEL_COVERAGE_GAP_TYPE),
          inArray(gaps.id, coveredIds),
          sql`${gaps.status} IN ('open', 'queued', 'asked')`,
        ),
      );
  }

  for (const omission of reconciliation.omissions) {
    const gapId = idsByRef.get(omission.ref)!;
    await args.db
      .insert(gaps)
      .values({
        id: gapId,
        gapType: MODEL_COVERAGE_GAP_TYPE,
        questionToAsk: `Administrative coverage finding: create or link an evidence claim for ${omission.kind} ${omission.localId}.`,
        whyItMatters: `Source ${args.sourceType} ${args.sourceId}, map ${args.activeMap.mapId}, ${omission.shape} ${omission.elementKind} ${omission.ref} has no current evidence claim. This is model-quality work and must not be asked directly to an employee.`,
        priority: 'medium',
        status: 'open',
      })
      .onConflictDoUpdate({
        target: gaps.id,
        set: {
          status: 'open',
          questionToAsk: `Administrative coverage finding: create or link an evidence claim for ${omission.kind} ${omission.localId}.`,
          whyItMatters: `Source ${args.sourceType} ${args.sourceId}, map ${args.activeMap.mapId}, ${omission.shape} ${omission.elementKind} ${omission.ref} has no current evidence claim. This is model-quality work and must not be asked directly to an employee.`,
          updatedAt: new Date(),
        },
      });
  }
  return reconciliation;
}
