import { existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { and, eq, isNotNull } from 'drizzle-orm';
import { Storage } from '@google-cloud/storage';
import { GoogleGenAI } from '@google/genai';
import { providerCachedContent, type OracleDb } from '@oracle/db';
import { recordCacheTermination } from '@oracle/engines';

function ensureGoogleApplicationCredentialsFromJson(): void {
  const json = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
  if (!json) return;
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) return;
  const tmpPath = join(tmpdir(), 'oracle-gcp-application-default-credentials.json');
  if (!existsSync(tmpPath)) {
    writeFileSync(tmpPath, json, { mode: 0o600 });
  }
  process.env.GOOGLE_APPLICATION_CREDENTIALS = tmpPath;
}

function getUploadedObjectName(metadata: unknown): string | null {
  if (!metadata || typeof metadata !== 'object') return null;
  const objectName = (metadata as { uploadedObjectName?: unknown }).uploadedObjectName;
  return typeof objectName === 'string' && objectName.length > 0 ? objectName : null;
}

async function cleanupUploadedGcsObject(metadata: unknown): Promise<void> {
  const objectName = getUploadedObjectName(metadata);
  const bucketName = process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET;
  if (!objectName || !bucketName) return;
  await new Storage().bucket(bucketName).file(objectName).delete({ ignoreNotFound: true });
}

export async function releaseVertexExplicitCaches(args: {
  db: OracleDb;
  sourceHash: string;
  cleanupOwner: string;
  createdByJobRunId?: string;
  reason: string;
  limit?: number;
}): Promise<{ deleted: number; failed: number }> {
  ensureGoogleApplicationCredentialsFromJson();
  const project = process.env.GOOGLE_CLOUD_PROJECT;
  const location = process.env.GOOGLE_CLOUD_LOCATION ?? 'us-central1';
  if (!project) {
    console.warn('[vertex-cache-cleanup] GOOGLE_CLOUD_PROJECT is unset; skipping explicit cache release');
    return { deleted: 0, failed: 0 };
  }

  const db = args.db;
  const rows = await db
    .select({
      id: providerCachedContent.id,
      providerResourceName: providerCachedContent.providerResourceName,
      providerMetadataJson: providerCachedContent.providerMetadataJson,
    })
    .from(providerCachedContent)
    .where(
      and(
        eq(providerCachedContent.provider, 'vertex'),
        eq(providerCachedContent.cacheKind, 'explicit'),
        eq(providerCachedContent.status, 'active'),
        eq(providerCachedContent.sourceHash, args.sourceHash),
        eq(providerCachedContent.cleanupOwner, args.cleanupOwner),
        args.createdByJobRunId
          ? eq(providerCachedContent.createdByJobRunId, args.createdByJobRunId)
          : undefined,
        isNotNull(providerCachedContent.providerResourceName),
      ),
    )
    .limit(args.limit ?? 20);

  if (rows.length === 0) return { deleted: 0, failed: 0 };

  const client = new GoogleGenAI({ vertexai: true, project, location });
  let deleted = 0;
  let failed = 0;
  for (const row of rows) {
    try {
      if (row.providerResourceName) {
        await client.caches.delete({ name: row.providerResourceName });
      }
      await cleanupUploadedGcsObject(row.providerMetadataJson);
      await recordCacheTermination({
        db,
        handle: { id: row.id },
        status: 'deleted',
        reason: args.reason,
      });
      deleted += 1;
    } catch (err) {
      failed += 1;
      await recordCacheTermination({
        db,
        handle: { id: row.id },
        status: 'failed',
        reason:
          `${args.reason}; provider cache delete failed: ` +
          (err instanceof Error ? err.message : String(err)),
      });
    }
  }

  return { deleted, failed };
}
