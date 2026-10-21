// S02-backed authority for the S03 pilot web path.
// Mirrors services/oracle-brain/oracle_brain/authz.has_authority against
// oracle2.appointments. Fails closed when ORACLE2_DATABASE_URL is missing —
// a real-data journey never runs on memory grants.

import { pilotPostgres } from '@/lib/oracle2-postgres';

export type PilotScope = 'review' | 'confirm';

function databaseUrl(): string | undefined {
  return process.env.ORACLE2_DATABASE_URL;
}

function workspaceId(): string {
  return process.env.ORACLE2_PILOT_WORKSPACE_ID ?? '00000000-0000-4000-8000-000000000002';
}

function sql() {
  const url = databaseUrl();
  if (!url) {
    throw new Error('ORACLE2_DATABASE_URL is required for store-backed authority');
  }
  return pilotPostgres(url);
}

// Each step in the chain must prove its parent issued it: the join on
// parent_id is paired with an issuer-link check (l.granted_by = p.actor_id).
// A child whose granted_by does not match its claimed parent's actor_id is
// rejected — an unrelated root cannot confer access through a forged parent_id.
// Ancestor scope: every parent must itself hold the claimed scope or be root.
// A confirm grant chained through a review-only parent is denied.
const HAS_AUTHORITY_SQL = `
WITH RECURSIVE lineage AS (
  SELECT a.appointment_id AS start_id,a.appointment_id,a.parent_id,
         a.revoked_at,a.expires_at,a.scope,a.actor_id,a.granted_by,
         a.workspace_id,1 AS depth
  FROM oracle2.appointments a
  WHERE a.workspace_id=$1 AND a.actor_id=$2
    AND a.scope IN ($3,'root')
  UNION ALL
  SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,
         p.scope,p.actor_id,p.granted_by,p.workspace_id,l.depth+1
  FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id
  WHERE l.depth<16 AND p.workspace_id=l.workspace_id
    AND l.granted_by=p.actor_id
    AND p.scope IN ($3,'root')
)
SELECT EXISTS (
  SELECT 1 FROM lineage GROUP BY start_id
  HAVING bool_and(revoked_at IS NULL AND
                  (expires_at IS NULL OR expires_at>now()))
     AND bool_or(scope='root' AND parent_id IS NULL)
) AS ok
`;

/** Shape of an oracle2.appointments row used by the pure chain validator. */
export type AppointmentRow = {
  appointment_id: string;
  workspace_id: string;
  actor_id: string;
  scope: string;
  granted_by: string;
  parent_id: string | null;
  revoked_at: string | null;
  expires_at: string | null;
};

/**
 * Pure mirror of HAS_AUTHORITY_SQL: proves the scope through an unbroken
 * issuer-linked chain that reaches a root. Each grant must show its parent
 * issued it (parent_id link AND granted_by = parent.actor_id). Every ancestor
 * must itself hold the claimed scope or be root — a child cannot hold a scope
 * its parent did not hold. Unrelated roots and confirm-through-review are
 * rejected. Used by tests; the SQL is the production enforcement.
 */
export function lineageAuthorizes(
  appointments: AppointmentRow[],
  actorId: string,
  scope: string,
  workspaceId: string,
  now: Date = new Date(),
): boolean {
  const byId = new Map(appointments.map((a) => [a.appointment_id, a]));
  // Start from the actor's grants with the target scope or root.
  const starts = appointments.filter(
    (a) =>
      a.workspace_id === workspaceId &&
      a.actor_id === actorId &&
      (a.scope === scope || a.scope === 'root'),
  );
  for (const start of starts) {
    // Walk up parent_id links; every step must prove issuer link and scope.
    const chain: AppointmentRow[] = [start];
    let current = start;
    let valid = true;
    const seen = new Set<string>([start.appointment_id]);
    for (let depth = 1; depth < 16; depth++) {
      if (current.parent_id === null) break;
      const parent = byId.get(current.parent_id);
      if (!parent || parent.workspace_id !== current.workspace_id) {
        valid = false;
        break;
      }
      // Issuer link: the parent's actor must have issued the child.
      if (current.granted_by !== parent.actor_id) {
        valid = false;
        break;
      }
      // Ancestor scope: a child cannot hold a scope its parent did not hold.
      if (parent.scope !== scope && parent.scope !== 'root') {
        valid = false;
        break;
      }
      if (seen.has(parent.appointment_id)) {
        valid = false;
        break;
      }
      seen.add(parent.appointment_id);
      chain.push(parent);
      current = parent;
    }
    if (!valid) continue;
    // Every step unrevoked and unexpired.
    const allLive = chain.every(
      (a) => a.revoked_at === null && (a.expires_at === null || new Date(a.expires_at) > now),
    );
    if (!allLive) continue;
    // The chain must reach a root anchor.
    const reachesRoot = chain.some((a) => a.scope === 'root' && a.parent_id === null);
    if (reachesRoot) return true;
  }
  return false;
}

/**
 * True only when the store-backed appointment lineage proves the scope in the
 * given workspace. Defaults to the pilot workspace; callers that authorize a
 * different workspace resource must pass that workspace id explicitly so pilot
 * permissions are never inherited across workspaces.
 */
export async function hasAuthority(
  actorId: string,
  scope: PilotScope,
  workspaceIdOverride?: string,
): Promise<boolean> {
  if (!actorId) return false;
  if (!databaseUrl()) return false;
  const client = sql();
  try {
    const rows = await client.unsafe(HAS_AUTHORITY_SQL, [
      workspaceIdOverride ?? workspaceId(),
      actorId,
      scope,
    ]);
    return Boolean(rows[0]?.ok);
  } catch {
    return false;
  } finally {
    await client.end({ timeout: 1 });
  }
}

/**
 * Insert a non-root appointment. The parent_id links the new grant to the
 * grantor's appointment so the chain can prove the issuer link; parent must
 * already hold the scope or root.
 */
export async function delegateScope(
  grantorId: string,
  actorId: string,
  scope: PilotScope,
): Promise<void> {
  if (!databaseUrl()) {
    throw new Error('ORACLE2_DATABASE_URL is required to delegate authority');
  }
  if (actorId === grantorId) {
    throw new Error('actor_id <> granted_by');
  }
  const client = sql();
  try {
    // Resolve the grantor's anchoring appointment (unrevoked, unexpired).
    const parentRows = await client.unsafe(
      `SELECT appointment_id FROM oracle2.appointments
       WHERE workspace_id=$1 AND actor_id=$2
         AND scope IN ($3,'root')
         AND revoked_at IS NULL
         AND (expires_at IS NULL OR expires_at>now())
       ORDER BY appointment_id LIMIT 1`,
      [workspaceId(), grantorId, scope],
    );
    const parentId: string | null = parentRows[0]?.appointment_id ?? null;
    await client`
      INSERT INTO oracle2.appointments
        (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
      VALUES (gen_random_uuid(),${workspaceId()}::uuid,${actorId}::uuid,${scope},${grantorId}::uuid,${parentId}::uuid)
    `;
  } finally {
    await client.end({ timeout: 1 });
  }
}
