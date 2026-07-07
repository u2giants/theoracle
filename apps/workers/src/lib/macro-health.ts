import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';

/**
 * Document-level macro (holistic layer) health, surfaced in Admin -> Documents so
 * a document whose macro layer failed can never read as a green `complete`.
 *
 * Precedence (worst wins, race-tolerant so the fire-and-forget followups can
 * finish in any order): failed > degraded > complete > pending > not_applicable.
 *
 *   - markMacroPending  — set when document-ingestion dispatches the outline (fresh run).
 *   - markMacroComplete — a followup succeeded and nothing has failed yet.
 *   - markMacroDegraded — a macro/coverage followup failed (partial holistic layer).
 *   - markMacroMapFailed — the source workflow map failed; blind extraction may still continue.
 *   - markMacroFailed    — a hard macro failure should block the document.
 *
 * The conditional WHERE clauses make these safe to call concurrently: a success
 * can never overwrite a recorded failure, and a failure always downgrades.
 */
export type MacroHealth =
  | 'not_applicable'
  | 'pending'
  | 'complete'
  | 'map_failed'
  | 'map_degraded'
  | 'merge_pending_review'
  | 'degraded'
  | 'failed';

async function setMacroHealth(
  db: OracleDb,
  documentId: string | null | undefined,
  value: MacroHealth,
  onlyWhenIn?: MacroHealth[],
): Promise<void> {
  if (!documentId) return;
  const guard = onlyWhenIn?.length
    ? sql` AND macro_health IN (${sql.join(
        onlyWhenIn.map((v) => sql`${v}`),
        sql`, `,
      )})`
    : sql``;
  try {
    await db.execute(sql`
      UPDATE documents
      SET macro_health = ${value}
      WHERE id = ${documentId}::uuid${guard}
    `);
  } catch (err) {
    // Health is observability, never load-bearing — a failed health write must
    // not mask or replace the real worker outcome.
    console.warn('[macro-health] failed to set', { documentId, value, err });
  }
}

export function markMacroPending(db: OracleDb, documentId?: string | null): Promise<void> {
  return setMacroHealth(db, documentId, 'pending');
}

export function markMacroComplete(db: OracleDb, documentId?: string | null): Promise<void> {
  // Only promote to complete if nothing has failed/degraded this run.
  return setMacroHealth(db, documentId, 'complete', ['pending']);
}

export function markMacroDegraded(db: OracleDb, documentId?: string | null): Promise<void> {
  // Downgrade from pending/complete; never overwrite a hard 'failed'.
  return setMacroHealth(db, documentId, 'degraded', ['pending', 'complete']);
}

export function markMacroMapFailed(db: OracleDb, documentId?: string | null): Promise<void> {
  return setMacroHealth(db, documentId, 'map_failed');
}

export function markMacroFailed(db: OracleDb, documentId?: string | null): Promise<void> {
  return setMacroHealth(db, documentId, 'failed');
}
