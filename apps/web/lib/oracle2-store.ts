// Postgres-backed pilot journey store (oracle2 schema).
// Replaces the S03 in-memory maps for the preview journey so confirmation is
// transactional and evidence is durable. Role: oracle2_pilot_web (not admin).

import postgres from 'postgres';
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

export async function insertSource(input: {
  workspaceId: string;
  actorId: string;
  filename: string;
  contentType: string;
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
                ${input.actorId}::uuid,${'Pilot process'},${sql.json([])},'draft')
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
    const r = rows[0];
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
      if (rows[0].status !== 'draft') throw new Error('only draft-status documents can be corrected');
      await tx`
        UPDATE oracle2.drafts
        SET connections=${sql.json(input.connections)},
            process_name=COALESCE(${input.processName ?? null}, process_name),
            updated_at=now()
        WHERE draft_id=${input.draftId}::uuid
      `;
      await tx`
        INSERT INTO oracle2.reviews (review_id,draft_id,workspace_id,actor_id,action,payload)
        VALUES (${randomUUID()}::uuid,${input.draftId}::uuid,${input.workspaceId}::uuid,
                ${input.actorId}::uuid,'correct',${sql.json({ connections: input.connections })})
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
      if (rows[0].status === 'confirmed') throw new Error('draft already confirmed');
      if (rows[0].status === 'withdrawn') throw new Error('withdrawn draft cannot be confirmed');
      await tx`
        UPDATE oracle2.drafts SET status='confirmed', updated_at=now()
        WHERE draft_id=${input.draftId}::uuid
      `;
      await tx`
        INSERT INTO oracle2.reviews (review_id,draft_id,workspace_id,actor_id,action,payload)
        VALUES (${randomUUID()}::uuid,${input.draftId}::uuid,${input.workspaceId}::uuid,
                ${input.actorId}::uuid,'confirm',${sql.json({ scope: input.scope })})
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
              'completed',${sql.json(input.answer ?? {})})
    `;
    return runId;
  } finally {
    await sql.end({ timeout: 1 });
  }
}

export async function getRun(runId: string, workspaceId: string): Promise<StoredRun | null> {
  const sql = client();
  try {
    const rows = await sql`
      SELECT run_id::text, workspace_id::text, actor_id::text, source_id::text,
             draft_id::text, question, status, answer, error, created_at
      FROM oracle2.runs
      WHERE run_id=${runId}::uuid AND workspace_id=${workspaceId}::uuid
    `;
    if (rows.length === 0) return null;
    const r = rows[0];
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
