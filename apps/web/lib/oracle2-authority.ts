// S02-backed authority for the S03 pilot web path.
// Mirrors services/oracle-brain/oracle_brain/authz.has_authority against
// oracle2.appointments. Fails closed when ORACLE2_DATABASE_URL is missing —
// a real-data journey never runs on memory grants.

import postgres from 'postgres';

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
  return postgres(url, { max: 1, connect_timeout: 5 });
}

const HAS_AUTHORITY_SQL = `
WITH RECURSIVE lineage AS (
  SELECT a.appointment_id AS start_id,a.appointment_id,a.parent_id,
         a.revoked_at,a.expires_at,a.scope,a.actor_id,a.workspace_id,1 AS depth
  FROM oracle2.appointments a
  WHERE a.workspace_id=$1 AND a.actor_id=$2
    AND a.scope IN ($3,'root')
  UNION ALL
  SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,
         p.scope,p.actor_id,p.workspace_id,l.depth+1
  FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id
  WHERE l.depth<16 AND p.workspace_id=l.workspace_id
)
SELECT EXISTS (
  SELECT 1 FROM lineage GROUP BY start_id
  HAVING bool_and(revoked_at IS NULL AND
                  (expires_at IS NULL OR expires_at>now()))
     AND bool_or(scope='root' AND parent_id IS NULL)
) AS ok
`;

/** True only when the store-backed appointment lineage proves the scope. */
export async function hasAuthority(
  actorId: string,
  scope: PilotScope,
): Promise<boolean> {
  if (!actorId) return false;
  if (!databaseUrl()) return false;
  const client = sql();
  try {
    const rows = await client.unsafe(HAS_AUTHORITY_SQL, [
      workspaceId(),
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

/** Insert a non-root appointment (parent must already hold the scope or root). */
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
    await client`
      INSERT INTO oracle2.appointments
        (appointment_id,workspace_id,actor_id,scope,granted_by)
      VALUES (gen_random_uuid(),${workspaceId()}::uuid,${actorId}::uuid,${scope},${grantorId}::uuid)
    `;
  } finally {
    await client.end({ timeout: 1 });
  }
}
