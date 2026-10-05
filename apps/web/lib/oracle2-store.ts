// Postgres-backed pilot journey store (oracle2 schema).
// Replaces the S03 in-memory maps for the preview journey so confirmation is
// transactional and evidence is durable. Role: oracle2_pilot_web (not admin).

import postgres from 'postgres';
import type { TransactionSql } from 'postgres';
import { randomUUID } from 'crypto';
import type { DraftConnection, SourceBlock } from '@/lib/oracle2-client';

export type DraftStatus = 'draft' | 'confirmed' | 'withdrawn';

export interface StoredDraft {
  draftId: string;
  sourceId: string;
  workspaceId: string;
  createdBy: string;
  processName: string;
  connections: DraftConnection[];
  status: DraftStatus;
  updatedAt: string;
}

export interface StoredRun {
  runId: string;
  workspaceId: string;
  actorId: string;
  sourceId: string;
  draftId: string | null;
  question: string;
  status: string;
  answer: unknown;
  error: string | null;
  createdAt: string;
}

function databaseUrl(): string | undefined {
  return process.env.ORACLE2_DATABASE_URL;
}

export function pilotWorkspaceId(): string {
  return (
    process.env.ORACLE2_PILOT_WORKSPACE_ID ?? '00000000-0000-4000-8000-000000000002'
  );
}

function client() {
  const url = databaseUrl();
  if (!url) {
    throw new Error('ORACLE2_DATABASE_URL is required for the journey store');
  }
  return postgres(url, { max: 1, connect_timeout: 5 });
}

function asJson(value: unknown) {
  return JSON.stringify(value ?? null);
}

export async function insertSource(input: {
  workspaceId: string;
  actorId: string;
  filename: string;
  contentType: string;
  processName?: string;
  blocks: SourceBlock[];
}): Promise<{ sourceId: string; draftId: string }> {
  const sql = client();
  const sourceId = randomUUID();
  const draftId = randomUUID();
  try {
    await sql.begin(async (tx) => {
      await tx`
        INSERT INTO oracle2.sources
          (source_id,workspace_id,uploaded_by,filename,content_type,status)
        VALUES (${sourceId}::uuid,${input.workspaceId}::uuid,${input.actorId}::uuid,
                ${input.filename},${input.contentType},'draft')
      `;
      for (const block of input.blocks) {
        await tx`
          INSERT INTO oracle2.source_blocks
            (block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end)
          VALUES (${randomUUID()}::uuid,${sourceId}::uuid,${input.workspaceId}::uuid,
                  ${block.blockIndex},'paragraph',${block.text},${block.spanStart},${block.spanEnd})
        `;
      }
      await tx`
        INSERT INTO oracle2.drafts
          (draft_id,source_id,workspace_id,created_by,process_name,connections,status)
        VALUES (${draftId}::uuid,${sourceId}::uuid,${input.workspaceId}::uuid,
                ${input.actorId}::uuid,${input.processName ?? 'Pilot process'},${asJson([])},'draft')
      `;
    });
    return { sourceId, draftId };
  } finally {
    await sql.end({ timeout: 1 });
  }
}

export async function getSourceBlocks(
  sourceId: string,
  workspaceId: string,
): Promise<SourceBlock[]> {
  const sql = client();
  try {
    const rows = await sql`
      SELECT block_id::text, source_id::text, block_index, text, span_start, span_end
      FROM oracle2.source_blocks
      WHERE source_id=${sourceId}::uuid AND workspace_id=${workspaceId}::uuid
      ORDER BY block_index
    `;
    return rows.map((r) => ({
      blockId: r.block_id as string,
      sourceId: r.source_id as string,
      blockIndex: Number(r.block_index),
      text: r.text as string,
      spanStart: Number(r.span_start),
      spanEnd: Number(r.span_end),
    }));
  } finally {
    await sql.end({ timeout: 1 });
  }
}

export async function getDraft(
  draftId: string,
  workspaceId: string,
): Promise<StoredDraft | null> {
  const sql = client();
  try {
    const rows = await sql`
      SELECT draft_id::text, source_id::text, workspace_id::text, created_by::text,
             process_name, connections, status, updated_at
      FROM oracle2.drafts
      WHERE draft_id=${draftId}::uuid AND workspace_id=${workspaceId}::uuid
    `;
    if (rows.length === 0) return null;
    const r = rows[0]!;
    return {
      draftId: r.draft_id as string,
      sourceId: r.source_id as string,
      workspaceId: r.workspace_id as string,
      createdBy: r.created_by as string,
      processName: r.process_name as string,
      connections: (r.connections as DraftConnection[]) ?? [],
      status: r.status as DraftStatus,
      updatedAt: new Date(r.updated_at as string).toISOString(),
    };
  } finally {
    await sql.end({ timeout: 1 });
  }
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

async function assertAuthorityInTx(
  tx: TransactionSql,
  workspaceId: string,
  actorId: string,
  scope: 'review' | 'confirm',
): Promise<void> {
  // SHARE lock covers the appointment table without requiring UPDATE.
  await tx`LOCK TABLE oracle2.appointments IN SHARE MODE`;
  const rows = await tx.unsafe(HAS_AUTHORITY_SQL, [workspaceId, actorId, scope]);
  if (!rows[0]?.ok) {
    throw new Error(`actor lacks ${scope} authority`);
  }
}

export async function correctDraft(input: {
  draftId: string;
  workspaceId: string;
  actorId: string;
  connections: DraftConnection[];
  processName?: string;
}): Promise<void> {
  const sql = client();
  try {
    await sql.begin(async (tx) => {
      const rows = await tx`
        SELECT status FROM oracle2.drafts
        WHERE draft_id=${input.draftId}::uuid AND workspace_id=${input.workspaceId}::uuid
        FOR UPDATE
      `;
      if (rows.length === 0) throw new Error('draft not found');
      if (rows[0]!.status !== 'draft') throw new Error('only draft-status documents can be corrected');
      await assertAuthorityInTx(tx, input.workspaceId, input.actorId, 'review');
      await tx`
        UPDATE oracle2.drafts
        SET connections=${asJson(input.connections)},
            process_name=COALESCE(${input.processName ?? null}, process_name),
            updated_at=now()
        WHERE draft_id=${input.draftId}::uuid
      `;
      await tx`
        INSERT INTO oracle2.reviews (review_id,draft_id,workspace_id,actor_id,action,payload)
        VALUES (${randomUUID()}::uuid,${input.draftId}::uuid,${input.workspaceId}::uuid,
                ${input.actorId}::uuid,'correct',${asJson({ connections: input.connections })})
      `;
    });
  } finally {
    await sql.end({ timeout: 1 });
  }
}

export async function confirmDraft(input: {
  draftId: string;
  workspaceId: string;
  actorId: string;
  scope: string;
}): Promise<void> {
  const sql = client();
  try {
    await sql.begin(async (tx) => {
      const rows = await tx`
        SELECT status FROM oracle2.drafts
        WHERE draft_id=${input.draftId}::uuid AND workspace_id=${input.workspaceId}::uuid
        FOR UPDATE
      `;
      if (rows.length === 0) throw new Error('draft not found');
      if (rows[0]!.status === 'confirmed') throw new Error('draft already confirmed');
      if (rows[0]!.status === 'withdrawn') throw new Error('withdrawn draft cannot be confirmed');
      await assertAuthorityInTx(tx, input.workspaceId, input.actorId, 'confirm');
      const lineage = await tx`
        WITH RECURSIVE lineage AS (
          SELECT appointment_id, scope, parent_id, revoked_at, expires_at
          FROM oracle2.appointments
          WHERE workspace_id=${input.workspaceId}::uuid AND actor_id=${input.actorId}::uuid
          UNION ALL
          SELECT p.appointment_id, p.scope, p.parent_id, p.revoked_at, p.expires_at
          FROM oracle2.appointments p
          JOIN lineage l ON p.appointment_id = l.parent_id
          WHERE p.workspace_id=${input.workspaceId}::uuid
        )
        SELECT appointment_id::text, scope, parent_id::text
        FROM lineage
        WHERE revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())
      `;
      await tx`
        UPDATE oracle2.drafts SET status='confirmed', updated_at=now()
        WHERE draft_id=${input.draftId}::uuid
      `;
      await tx`
        INSERT INTO oracle2.reviews (review_id,draft_id,workspace_id,actor_id,action,payload)
        VALUES (${randomUUID()}::uuid,${input.draftId}::uuid,${input.workspaceId}::uuid,
                ${input.actorId}::uuid,'confirm',
                ${asJson({ scope: input.scope, authority: lineage })})
      `;
    });
  } finally {
    await sql.end({ timeout: 1 });
  }
}

export async function storeRun(input: {
  workspaceId: string;
  actorId: string;
  sourceId: string;
  draftId: string | null;
  question: string;
  answer: unknown;
}): Promise<string> {
  const sql = client();
  const runId = randomUUID();
  try {
    await sql`
      INSERT INTO oracle2.runs
        (run_id,workspace_id,actor_id,source_id,draft_id,question,status,answer)
      VALUES (${runId}::uuid,${input.workspaceId}::uuid,${input.actorId}::uuid,
              ${input.sourceId}::uuid,${input.draftId}::uuid,${input.question},
              'completed',${asJson(input.answer ?? {})})
    `;
    return runId;
  } finally {
    await sql.end({ timeout: 1 });
  }
}

export async function getRun(
  runId: string,
  workspaceId: string,
  actorId: string,
): Promise<StoredRun | null> {
  const sql = client();
  try {
    const rows = await sql`
      SELECT run_id::text, workspace_id::text, actor_id::text, source_id::text,
             draft_id::text, question, status, answer, error, created_at
      FROM oracle2.runs
      WHERE run_id=${runId}::uuid AND workspace_id=${workspaceId}::uuid
        AND actor_id=${actorId}::uuid
    `;
    if (rows.length === 0) return null;
    const r = rows[0]!;
    return {
      runId: r.run_id as string,
      workspaceId: r.workspace_id as string,
      actorId: r.actor_id as string,
      sourceId: r.source_id as string,
      draftId: (r.draft_id as string | null) ?? null,
      question: r.question as string,
      status: r.status as string,
      answer: r.answer,
      error: (r.error as string | null) ?? null,
      createdAt: new Date(r.created_at as string).toISOString(),
    };
  } finally {
    await sql.end({ timeout: 1 });
  }
}
