/**
 * VertexGeminiAdapter — direct Google Vertex AI integration via `@google/genai`.
 *
 * Architecture (DECISIONS.md D6, docs/oracle/02 §"Shared architecture"):
 * - Calls Vertex AI's REST API directly using Google's official GenAI SDK.
 * - NO Vercel AI SDK and NO OpenRouter in this path.
 * - Authenticates via Application Default Credentials. Set up locally with
 *   `gcloud auth application-default login`. In cloud runtime, mount a
 *   service-account JSON or use workload identity — the SDK auto-detects.
 * - Reads `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from env.
 *
 * Caching strategy:
 * - Implicit caching is automatic on Gemini's side; no client action needed.
 *   Cache hits show up as `usageMetadata.cachedContentTokenCount` and are
 *   normalized into `OracleUsage.cachedInputTokens`.
 * - For large reusable prefixes, this adapter creates explicit
 *   `cachedContent` resources, persists them through `provider_cached_content`,
 *   reuses them across worker processes by `source_hash`, and cleans them up
 *   once the hard TTL elapses.
 * - For oversized document artifacts, the adapter can upload a temporary cache
 *   source object to GCS and create the explicit cache from `fileData`
 *   instead of re-sending flattened text only.
 *
 * Structured output:
 * - Uses `responseMimeType: 'application/json'` + `responseJsonSchema:
 *   <jsonSchema>` (added in @google/genai 2.6). The JSON-schema mode is
 *   strict — Gemini enforces the schema on output. This is the direct
 *   capability that the OpenRouter -> Gemini bridge couldn't reach.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Google Vertex AI
 * / Gemini direct".
 */

import { writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { and, desc, eq, gt, isNotNull, lte } from 'drizzle-orm';
import { Storage } from '@google-cloud/storage';
import { GoogleGenAI } from '@google/genai';
import type { Content, GenerateContentResponse } from '@google/genai';
import { z, type ZodTypeAny } from 'zod';
import { providerCachedContent } from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import {
  recordCacheCreation,
  recordCacheReuse,
  recordCacheTermination,
  type CacheLifecycleHandle,
} from '@oracle/engines';
import type {
  OracleObjectResult,
  OraclePromptPlan,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute, ReasoningEffort } from '../routes';
import type {
  BatchResultItem,
  BatchStatus,
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
  RetrieveBatchArgs,
  RetrieveBatchResult,
  SubmitBatchArgs,
  SubmitBatchResult,
} from './types';
import {
  estimatePlanStableTokens,
  estimateTextTokens,
  getCacheHints,
  hashCacheKey,
  normalizeMessageContentArray,
  pickVertexCacheTtlSeconds,
  splitPlanForCaching,
  shouldDisableCache,
  type VertexFileCacheSource,
} from './cache-utils';

export interface VertexGeminiAdapterOptions {
  /** GCP project ID. Defaults to env GOOGLE_CLOUD_PROJECT. */
  project?: string;
  /** Vertex region. Defaults to env GOOGLE_CLOUD_LOCATION or 'us-central1'. */
  location?: string;
}

interface VertexExplicitCacheEntry {
  name: string;
  expiresAtMs: number;
  includesSystemInstruction: boolean;
  lifecycleHandle?: CacheLifecycleHandle;
}

/**
 * If `GOOGLE_APPLICATION_CREDENTIALS_JSON` is set but
 * `GOOGLE_APPLICATION_CREDENTIALS` (the file-path variant ADC reads) is not,
 * materialize the JSON to a temp file and point ADC at it. This is the
 * standard pattern for cloud workers (Trigger.dev, Vercel) that can hold
 * env-var secrets but not mount files. Local dev (where the file path is
 * already set by `gcloud auth application-default login`) is unaffected.
 *
 * Runs at most once per worker process — the temp file is reused.
 */
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

export class VertexGeminiAdapter implements OracleProviderAdapter {
  readonly provider = 'vertex' as const;
  private readonly client: GoogleGenAI;
  private readonly explicitCacheByKey = new Map<string, VertexExplicitCacheEntry>();
  private storageClient: Storage | null = null;

  constructor(opts: VertexGeminiAdapterOptions = {}) {
    ensureGoogleApplicationCredentialsFromJson();
    const project = opts.project ?? process.env.GOOGLE_CLOUD_PROJECT;
    const location =
      opts.location ?? process.env.GOOGLE_CLOUD_LOCATION ?? 'us-central1';
    if (!project) {
      throw new Error(
        'VertexGeminiAdapter: GOOGLE_CLOUD_PROJECT is not set. ' +
          'Set it in .env.local or pass {project} explicitly.',
      );
    }
    this.client = new GoogleGenAI({ vertexai: true, project, location });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, prefixContext, dynamicInput } = splitPlanForCaching(plan);
    const userMessage = [prefixContext, dynamicInput].filter(Boolean).join('\n\n');
    await this.cleanupExpiredExplicitCaches();
    await this.cleanupExpiredPersistentCaches();
    const contents = this.buildContents(userMessage, providerOptions);
    const explicitCache = shouldDisableCache(providerOptions)
      ? null
      : await this.prepareExplicitCacheForText(plan, route.modelId, systemPrompt, contents, providerOptions);
    const callStartedAt = Date.now();

    const response = await this.client.models.generateContent({
      model: route.modelId,
      contents: explicitCache?.contentsForRequest ?? contents,
      config: {
        systemInstruction: explicitCache?.omitSystemInstruction
          ? undefined
          : systemPrompt || undefined,
        temperature:
          typeof providerOptions?.temperature === 'number'
            ? providerOptions.temperature
            : undefined,
        ...(explicitCache?.cacheName ? { cachedContent: explicitCache.cacheName } : {}),
        ...vertexThinkingConfig(route.reasoningEffort),
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    await this.recordSuccessfulExplicitCacheReuse(explicitCache);
    return {
      text: response.text ?? '',
      usage: this.normalizeUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema, providerOptions } = args;
    const { systemPrompt, prefixContext, dynamicInput } = splitPlanForCaching(plan);
    const userMessage = [prefixContext, dynamicInput].filter(Boolean).join('\n\n');
    const jsonSchema = zodToJsonSchema(schema);
    await this.cleanupExpiredExplicitCaches();
    await this.cleanupExpiredPersistentCaches();
    const explicitCache = shouldDisableCache(providerOptions)
      ? null
      : await this.prepareExplicitCacheForObject(plan, route.modelId, systemPrompt, providerOptions);
    const callStartedAt = Date.now();

    const response = await this.client.models.generateContent({
      model: route.modelId,
      contents: [{ role: 'user', parts: [{ text: explicitCache?.requestUserMessage ?? userMessage }] }],
      config: {
        systemInstruction: explicitCache?.omitSystemInstruction
          ? undefined
          : systemPrompt || undefined,
        temperature: 0.1,
        responseMimeType: 'application/json',
        // responseJsonSchema accepts standard JSON Schema as of @google/genai 2.6.
        responseJsonSchema: jsonSchema as unknown,
        ...(explicitCache?.cacheName ? { cachedContent: explicitCache.cacheName } : {}),
        ...vertexThinkingConfig(route.reasoningEffort),
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    await this.recordSuccessfulExplicitCacheReuse(explicitCache);
    const text = response.text ?? '';
    const parsed = JSON.parse(text);
    // Best-effort runtime validation if a Zod schema was supplied — gives the
    // caller a typed error rather than silently passing through malformed output.
    const validated = tryZodParse<TOutput>(schema, parsed);
    return {
      object: (validated ?? parsed) as TOutput,
      usage: this.normalizeUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  /**
   * Translate `providerOptions.messages` (a multi-turn array shaped for the
   * Vercel AI SDK / OpenAI chat format) into Vertex's `contents` shape, or
   * fall back to a single user turn when no override is present.
   */
  private buildContents(
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): Content[] {
    const messages = providerOptions?.messages as
      | Array<{ role: 'user' | 'assistant' | 'system'; content: string }>
      | undefined;
    if (Array.isArray(messages) && messages.length > 0) {
      // Vertex uses 'model' instead of 'assistant'; system goes in
      // systemInstruction not contents.
      return messages
        .filter((m) => m.role !== 'system')
        .map((m) => ({
          role: m.role === 'assistant' ? 'model' : 'user',
          parts: [{ text: m.content }],
        }));
    }
    return [{ role: 'user', parts: [{ text: userMessage }] }];
  }

  private async prepareExplicitCacheForText(
    plan: OraclePromptPlan,
    modelId: string,
    systemPrompt: string,
    contents: Content[],
    providerOptions?: Record<string, unknown>,
  ): Promise<{
    cacheName?: string;
    omitSystemInstruction: boolean;
      contentsForRequest: Content[];
      requestUserMessage?: string;
      lifecycleHandle?: CacheLifecycleHandle;
  } | null> {
    const hints = getCacheHints(providerOptions);
    const fileCache = await this.prepareExplicitFileCache(plan, modelId, systemPrompt, providerOptions);
    if (fileCache) {
      return {
        cacheName: fileCache.name,
        omitSystemInstruction: true,
        contentsForRequest: [{ role: 'user', parts: [{ text: fileCache.dynamicInput }] }],
        requestUserMessage: fileCache.dynamicInput,
        lifecycleHandle: fileCache.lifecycleHandle,
      };
    }
    const prefixContents = contents.slice(0, -1);
    const latestTurn = contents[contents.length - 1];
    const prefixText = prefixContents
      .flatMap((content) => content.parts ?? [])
      .map((part) => String(part.text ?? ''))
      .join('\n');
    const stableTokens = estimatePlanStableTokens(plan);
    const prefixTokens = estimateTextTokens(prefixText);
    const shouldCreate =
      hints?.preferExplicitCache === true ||
      prefixTokens >= 2048 ||
      stableTokens >= 2048;
    if (!shouldCreate || !latestTurn) return null;

    const cachePayload = prefixContents.length > 0
      ? { contents: prefixContents, includesSystemInstruction: !!systemPrompt }
      : { contents: [], includesSystemInstruction: !!systemPrompt };
    const sourceText = [systemPrompt, prefixContents.length > 0 ? prefixText : '']
      .filter(Boolean)
      .join('\n\n');
    const explicitCache = await this.getOrCreateExplicitCache({
      modelId,
      systemInstruction: systemPrompt || undefined,
      contents: cachePayload.contents,
      ttlSeconds: pickVertexCacheTtlSeconds(plan.taskType, providerOptions),
      cacheKey: hashCacheKey([
        modelId,
        plan.metadata.stablePrefixHash,
        prefixContents.length > 0 ? prefixText : '',
      ]),
      sourceHash: hashCacheKey([
        plan.metadata.stablePrefixHash,
        prefixContents.length > 0 ? prefixText : '',
      ]),
      sourceTokenEstimate: estimateTextTokens(sourceText),
      sourceDescription:
        hints?.sourceDescription ?? `${plan.taskType} reusable prefix`,
      expectedReuseCount: Math.max(1, hints?.expectedReuseCount ?? 1),
      latestPlannedReuseStep: hints?.latestPlannedReuseStep ?? plan.taskType,
      cleanupOwner: hints?.cleanupOwner,
      createdByJobRunId: hints?.createdByJobRunId,
      persistRecord: hints?.persistProviderCacheRecord === true,
    });
    if (!explicitCache) return null;
    return {
      cacheName: explicitCache.name,
      omitSystemInstruction: cachePayload.includesSystemInstruction,
      contentsForRequest: [latestTurn],
      lifecycleHandle: explicitCache.lifecycleHandle,
    };
  }

  private async prepareExplicitCacheForObject(
    plan: OraclePromptPlan,
    modelId: string,
    systemPrompt: string,
    providerOptions?: Record<string, unknown>,
  ): Promise<{
    cacheName?: string;
    omitSystemInstruction: boolean;
    requestUserMessage?: string;
    lifecycleHandle?: CacheLifecycleHandle;
  } | null> {
    const hints = getCacheHints(providerOptions);
    const fileCache = await this.prepareExplicitFileCache(plan, modelId, systemPrompt, providerOptions);
    if (fileCache) {
      return {
        cacheName: fileCache.name,
        omitSystemInstruction: true,
        requestUserMessage: fileCache.dynamicInput,
        lifecycleHandle: fileCache.lifecycleHandle,
      };
    }
    const stableTokens = estimatePlanStableTokens(plan);
    if (!(hints?.preferExplicitCache === true || stableTokens >= 2048) || !systemPrompt) {
      return null;
    }
    const explicitCache = await this.getOrCreateExplicitCache({
      modelId,
      systemInstruction: systemPrompt,
      contents: [],
      ttlSeconds: pickVertexCacheTtlSeconds(plan.taskType, providerOptions),
      cacheKey: hashCacheKey([modelId, plan.metadata.stablePrefixHash, 'system-only']),
      sourceHash: hashCacheKey([plan.metadata.stablePrefixHash, 'system-only']),
      sourceTokenEstimate: estimateTextTokens(systemPrompt),
      sourceDescription:
        hints?.sourceDescription ?? `${plan.taskType} system prefix`,
      expectedReuseCount: Math.max(1, hints?.expectedReuseCount ?? 1),
      latestPlannedReuseStep: hints?.latestPlannedReuseStep ?? plan.taskType,
      cleanupOwner: hints?.cleanupOwner,
      createdByJobRunId: hints?.createdByJobRunId,
      persistRecord: hints?.persistProviderCacheRecord === true,
    });
    if (!explicitCache) return null;
    return {
      cacheName: explicitCache.name,
      omitSystemInstruction: true,
      lifecycleHandle: explicitCache.lifecycleHandle,
    };
  }

  private async getOrCreateExplicitCache(input: {
    modelId: string;
    systemInstruction?: string;
    contents: Content[];
    ttlSeconds: number;
    cacheKey: string;
    sourceHash: string;
    sourceTokenEstimate: number;
    sourceDescription: string;
    expectedReuseCount: number;
    latestPlannedReuseStep?: string;
    cleanupOwner?: string;
    createdByJobRunId?: string;
    persistRecord: boolean;
    providerMetadataJson?: unknown;
  }): Promise<{ name: string; lifecycleHandle?: CacheLifecycleHandle } | null> {
    const existing = this.explicitCacheByKey.get(input.cacheKey);
    if (existing && existing.expiresAtMs > Date.now()) {
      return { name: existing.name, lifecycleHandle: existing.lifecycleHandle };
    }

    if (input.persistRecord) {
      const persisted = await this.getPersistedExplicitCache(input);
      if (persisted) return persisted;
    }
    try {
      const created = await this.client.caches.create({
        model: input.modelId,
        config: {
          contents: input.contents,
          systemInstruction: input.systemInstruction,
          displayName: `oracle-${input.cacheKey.slice(0, 32)}`,
          ttl: `${Math.max(60, input.ttlSeconds)}s`,
        },
      });
      const name = created.name;
      if (!name) return null;
      const expiresAtMs = Date.now() + Math.max(60, input.ttlSeconds) * 1000;
      const lifecycleHandle = input.persistRecord
        ? await recordCacheCreation({
            db: getDirectDb(),
            provider: 'vertex',
            cacheKind: 'explicit',
            sourceHash: input.sourceHash,
            sourceTokenEstimate: input.sourceTokenEstimate,
            sourceDescription: input.sourceDescription,
            providerResourceName: name,
            expectedReuseCount: input.expectedReuseCount,
            latestPlannedReuseStep: input.latestPlannedReuseStep,
            hardExpirationAt: new Date(expiresAtMs),
            cleanupOwner: input.cleanupOwner,
            createdByJobRunId: input.createdByJobRunId,
            providerMetadataJson: input.providerMetadataJson,
          })
        : undefined;
      this.explicitCacheByKey.set(input.cacheKey, {
        name,
        expiresAtMs,
        includesSystemInstruction: !!input.systemInstruction,
        lifecycleHandle,
      });
      return { name, lifecycleHandle };
    } catch (err) {
      console.warn(
        `[VertexGeminiAdapter] explicit cache create failed; falling back to implicit cache: ${
          err instanceof Error ? err.message : String(err)
        }`,
      );
      return null;
    }
  }

  private async prepareExplicitFileCache(
    plan: OraclePromptPlan,
    modelId: string,
    systemPrompt: string,
    providerOptions?: Record<string, unknown>,
  ): Promise<{
    name: string;
    dynamicInput: string;
    lifecycleHandle?: CacheLifecycleHandle;
  } | null> {
    const hints = getCacheHints(providerOptions);
    const fileSource = hints?.vertexFileCacheSource;
    if (!fileSource || hints?.preferExplicitCache !== true) return null;

    const { dynamicInput } = splitPlanForCaching(plan);
    const gcsUpload = await this.ensureVertexCacheFileUri(fileSource);
    if (!gcsUpload?.fileUri) return null;

    const explicitCache = await this.getOrCreateExplicitCache({
      modelId,
      systemInstruction: systemPrompt,
      contents: [
        {
          role: 'user',
          parts: [
            {
              fileData: {
                fileUri: gcsUpload.fileUri,
                mimeType: fileSource.mimeType,
              },
            },
          ],
        },
      ],
      ttlSeconds: pickVertexCacheTtlSeconds(plan.taskType, providerOptions),
      cacheKey: hashCacheKey([
        modelId,
        plan.metadata.stablePrefixHash,
        fileSource.sourceHash ?? fileSource.gcsUri ?? fileSource.localPath,
        'file-backed',
      ]),
      sourceHash: fileSource.sourceHash ??
        hashCacheKey([plan.metadata.stablePrefixHash, fileSource.gcsUri ?? fileSource.localPath, 'file-backed']),
      sourceTokenEstimate: estimatePlanStableTokens(plan),
      sourceDescription: hints?.sourceDescription ?? `${plan.taskType} file-backed cache`,
      expectedReuseCount: Math.max(1, hints?.expectedReuseCount ?? 1),
      latestPlannedReuseStep: hints?.latestPlannedReuseStep ?? plan.taskType,
      cleanupOwner: hints?.cleanupOwner,
      createdByJobRunId: hints?.createdByJobRunId,
      persistRecord: hints?.persistProviderCacheRecord === true,
      providerMetadataJson: gcsUpload.objectName
        ? {
            uploadedGcsUri: gcsUpload.fileUri,
            uploadedObjectName: gcsUpload.objectName,
            mimeType: fileSource.mimeType,
          }
        : undefined,
    });
    if (!explicitCache) return null;
    return {
      name: explicitCache.name,
      dynamicInput,
      lifecycleHandle: explicitCache.lifecycleHandle,
    };
  }

  private async ensureVertexCacheFileUri(fileSource: VertexFileCacheSource): Promise<{
    fileUri: string;
    objectName?: string;
  } | null> {
    if (fileSource.gcsUri) return { fileUri: fileSource.gcsUri };
    if (!fileSource.localPath) return null;
    const bucketName = process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET;
    if (!bucketName) {
      console.warn('[VertexGeminiAdapter] GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET is unset; skipping file-backed cache path');
      return null;
    }
    const prefix = process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX ?? 'oracle-context-cache';
    const objectName = `${prefix}/${fileSource.sourceHash ?? hashCacheKey([fileSource.localPath, fileSource.fileName])}-${fileSource.fileName ?? 'source'}`;
    const storage = this.getStorageClient();
    await storage.bucket(bucketName).upload(fileSource.localPath, {
      destination: objectName,
      metadata: {
        contentType: fileSource.mimeType,
      },
    });
    return {
      fileUri: `gs://${bucketName}/${objectName}`,
      objectName,
    };
  }

  private getStorageClient(): Storage {
    if (!this.storageClient) {
      this.storageClient = new Storage();
    }
    return this.storageClient;
  }

  private async getPersistedExplicitCache(input: {
    cacheKey: string;
    sourceHash: string;
    systemInstruction?: string;
  }): Promise<{ name: string; lifecycleHandle?: CacheLifecycleHandle } | null> {
    const db = getDirectDb();
    const [row] = await db
      .select({
        id: providerCachedContent.id,
        providerResourceName: providerCachedContent.providerResourceName,
        hardExpirationAt: providerCachedContent.hardExpirationAt,
      })
      .from(providerCachedContent)
      .where(
        and(
          eq(providerCachedContent.provider, 'vertex'),
          eq(providerCachedContent.status, 'active'),
          eq(providerCachedContent.sourceHash, input.sourceHash),
          isNotNull(providerCachedContent.providerResourceName),
          gt(providerCachedContent.hardExpirationAt, new Date()),
        ),
      )
      .orderBy(desc(providerCachedContent.createdAt))
      .limit(1);

    if (!row?.providerResourceName) return null;

    try {
      await this.client.caches.get({ name: row.providerResourceName });
      const expiresAtMs = new Date(row.hardExpirationAt).getTime();
      this.explicitCacheByKey.set(input.cacheKey, {
        name: row.providerResourceName,
        expiresAtMs,
        includesSystemInstruction: !!input.systemInstruction,
        lifecycleHandle: { id: row.id },
      });
      return { name: row.providerResourceName, lifecycleHandle: { id: row.id } };
    } catch (err) {
      await recordCacheTermination({
        db,
        handle: { id: row.id },
        status: 'orphaned',
        reason:
          'persisted Vertex cache lookup failed before reuse: ' +
          (err instanceof Error ? err.message : String(err)),
      });
      return null;
    }
  }

  private async cleanupExpiredExplicitCaches(): Promise<void> {
    const now = Date.now();
    const expired = [...this.explicitCacheByKey.entries()].filter(([, entry]) => entry.expiresAtMs <= now);
    if (expired.length === 0) return;
    for (const [key, entry] of expired) {
      this.explicitCacheByKey.delete(key);
      try {
        await this.client.caches.delete({ name: entry.name });
        await this.cleanupUploadedGcsObject(entry.lifecycleHandle);
        if (entry.lifecycleHandle) {
          await recordCacheTermination({
            db: getDirectDb(),
            handle: entry.lifecycleHandle,
            status: 'expired',
            reason: 'local explicit-cache TTL elapsed; provider cache deleted',
          });
        }
      } catch {
        if (entry.lifecycleHandle) {
          await recordCacheTermination({
            db: getDirectDb(),
            handle: entry.lifecycleHandle,
            status: 'failed',
            reason: 'local explicit-cache TTL elapsed; provider cache delete failed',
          });
        }
      }
    }
  }

  private async cleanupExpiredPersistentCaches(): Promise<void> {
    const db = getDirectDb();
    const expiredRows = await db
      .select({
        id: providerCachedContent.id,
        providerResourceName: providerCachedContent.providerResourceName,
      })
      .from(providerCachedContent)
      .where(
        and(
          eq(providerCachedContent.provider, 'vertex'),
          eq(providerCachedContent.status, 'active'),
          lte(providerCachedContent.hardExpirationAt, new Date()),
        ),
      )
      .orderBy(providerCachedContent.hardExpirationAt)
      .limit(10);

    for (const row of expiredRows) {
      try {
        if (row.providerResourceName) {
          await this.client.caches.delete({ name: row.providerResourceName });
        }
        await this.cleanupUploadedGcsObject({ id: row.id });
        await recordCacheTermination({
          db,
          handle: { id: row.id },
          status: 'expired',
          reason: 'hard expiration elapsed; cache lifecycle sweeper retired provider cache',
        });
      } catch {
        await recordCacheTermination({
          db,
          handle: { id: row.id },
          status: 'failed',
          reason: 'hard expiration elapsed; provider cache delete failed during sweeper cleanup',
        });
      }
    }
  }

  private async recordSuccessfulExplicitCacheReuse(
    explicitCache:
      | {
          lifecycleHandle?: CacheLifecycleHandle;
        }
      | null,
  ): Promise<void> {
    if (!explicitCache?.lifecycleHandle) return;
    await recordCacheReuse(getDirectDb(), explicitCache.lifecycleHandle);
  }

  private async cleanupUploadedGcsObject(
    lifecycleHandle: CacheLifecycleHandle | undefined,
  ): Promise<void> {
    if (!lifecycleHandle) return;
    const db = getDirectDb();
    const [row] = await db
      .select({ providerMetadataJson: providerCachedContent.providerMetadataJson })
      .from(providerCachedContent)
      .where(eq(providerCachedContent.id, lifecycleHandle.id))
      .limit(1);
    const metadata = row?.providerMetadataJson as
      | { uploadedGcsUri?: string; uploadedObjectName?: string }
      | undefined;
    const objectName = metadata?.uploadedObjectName;
    const bucketName = process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET;
    if (!objectName || !bucketName) return;
    try {
      await this.getStorageClient().bucket(bucketName).file(objectName).delete({ ignoreNotFound: true });
    } catch {
      // Best-effort cleanup. Cache lifecycle status still reflects the cache resource teardown result.
    }
  }

  /**
   * Normalize Gemini usage into OracleUsage.
   *   - promptTokenCount        -> inputTokens
   *   - candidatesTokenCount    -> outputTokens
   *   - cachedContentTokenCount -> cachedInputTokens
   *   - thoughtsTokenCount      -> reasoningTokens (Gemini 2.5+ thinking)
   */
  private normalizeUsage(
    response: GenerateContentResponse,
    latencyMs: number,
  ): OracleUsage {
    const u = response.usageMetadata ?? {};
    return {
      inputTokens: u.promptTokenCount,
      outputTokens: u.candidatesTokenCount,
      cachedInputTokens: u.cachedContentTokenCount,
      reasoningTokens: u.thoughtsTokenCount,
      latencyMs,
      providerRequestId: response.responseId,
      rawUsageJson: u,
    };
  }

  // ─── Batch API (Vertex Batch Prediction with GCS-backed I/O) ──────────────
  //
  // Input/output runs through GCS — Vertex doesn't accept inline batch bodies
  // for Gemini. Requires GOOGLE_VERTEX_BATCH_GCS_BUCKET to be set with the
  // service account having Storage Object Admin on it. See docs/configuration.md.
  //
  // Vertex batch output preserves input ORDER but doesn't echo a user-supplied
  // request ID. The adapter records customIds in submission order and pairs
  // them with output lines at retrieve time via providerMetadata.

  /**
   * Submit a batch of generateContent requests via Vertex Batch Prediction.
   * Writes a JSONL input file to `gs://$BUCKET/oracle-batch-<uuid>/input.jsonl`,
   * targets `gs://$BUCKET/oracle-batch-<uuid>/output/` for results, and
   * returns the BatchJob resource name as providerBatchId.
   *
   * providerMetadata: { inputGcsUri, outputGcsPrefix, customIdsInOrder }
   */
  async submitBatch(args: SubmitBatchArgs): Promise<SubmitBatchResult> {
    const { route, requests, jsonSchema } = args;
    const bucketName = process.env.GOOGLE_VERTEX_BATCH_GCS_BUCKET;
    if (!bucketName) {
      throw new Error(
        'VertexGeminiAdapter.submitBatch: GOOGLE_VERTEX_BATCH_GCS_BUCKET is not set. ' +
          'Vertex Batch Prediction needs a GCS bucket for JSONL input/output. ' +
          'See docs/configuration.md.',
      );
    }
    const prefixOverride = process.env.GOOGLE_VERTEX_BATCH_GCS_PREFIX?.trim();
    const folderId = `oracle-batch-${randomUUID()}`;
    const objectPrefix = prefixOverride ? `${prefixOverride}/${folderId}` : folderId;
    const inputObjectName = `${objectPrefix}/input.jsonl`;
    const outputObjectPrefix = `${objectPrefix}/output/`;

    const customIdsInOrder: string[] = [];
    const lines: string[] = [];
    for (const req of requests) {
      customIdsInOrder.push(req.customId);
      const { systemPrompt, userMessage } = flattenPlan(req.plan);
      const contents: Content[] = [{
        role: 'user',
        parts: [{ text: userMessage }],
      }];
      const generationConfig: Record<string, unknown> = {
        temperature: jsonSchema ? 0.1 : undefined,
      };
      if (jsonSchema) {
        generationConfig.responseMimeType = 'application/json';
        generationConfig.responseJsonSchema = jsonSchema;
      }
      const thinkingCfg = vertexThinkingConfig(route.reasoningEffort);
      if ('thinkingConfig' in thinkingCfg) {
        Object.assign(generationConfig, thinkingCfg);
      }
      for (const k of Object.keys(generationConfig)) {
        if (generationConfig[k] === undefined) delete generationConfig[k];
      }

      const requestBody: Record<string, unknown> = { contents };
      if (systemPrompt) {
        requestBody.systemInstruction = { parts: [{ text: systemPrompt }] };
      }
      if (Object.keys(generationConfig).length > 0) {
        requestBody.generationConfig = generationConfig;
      }
      lines.push(JSON.stringify({ request: requestBody }));
    }
    const jsonl = lines.join('\n') + '\n';

    const storage = new Storage();
    const bucket = storage.bucket(bucketName);
    await bucket.file(inputObjectName).save(Buffer.from(jsonl, 'utf-8'), {
      contentType: 'application/jsonl',
      resumable: false,
    });

    const inputGcsUri = `gs://${bucketName}/${inputObjectName}`;
    const outputGcsPrefix = `gs://${bucketName}/${outputObjectPrefix}`;

    const batch = await this.client.batches.create({
      model: route.modelId,
      src: { format: 'jsonl', gcsUri: [inputGcsUri] },
      config: {
        dest: { format: 'jsonl', gcsUri: outputGcsPrefix },
        displayName: folderId,
      },
    });

    const providerBatchId = batch.name;
    if (!providerBatchId) {
      throw new Error('VertexGeminiAdapter.submitBatch: batch.name missing from response');
    }

    return {
      providerBatchId,
      providerMetadata: {
        inputGcsUri,
        outputGcsPrefix,
        customIdsInOrder,
        bucketName,
        outputObjectPrefix,
      },
    };
  }

  /**
   * Poll Vertex batch status. When the JobState reaches SUCCEEDED, list the
   * prediction output objects in GCS (`predictions*.jsonl` — Vertex shards
   * large outputs), concatenate them in order, and pair each line with the
   * customId at the same index in providerMetadata.customIdsInOrder.
   */
  async retrieveBatch(args: RetrieveBatchArgs): Promise<RetrieveBatchResult> {
    const { providerBatchId, providerMetadata } = args;
    const batch = await this.client.batches.get({ name: providerBatchId });
    const status = mapVertexBatchStatus(batch.state ?? '');

    if (status === 'in_progress' || status === 'submitted') {
      return {
        status,
        requestCount: undefined,
        completedCount: undefined,
        failedCount: undefined,
      };
    }

    if (status !== 'completed') {
      // failed / expired / canceled
      return {
        status,
        error: batch.error?.message ?? `state=${batch.state}`,
      };
    }

    const bucketName = providerMetadata.bucketName as string | undefined;
    const outputObjectPrefix = providerMetadata.outputObjectPrefix as string | undefined;
    const customIdsInOrder = providerMetadata.customIdsInOrder as string[] | undefined;
    if (!bucketName || !outputObjectPrefix || !customIdsInOrder) {
      return {
        status: 'failed',
        error: 'providerMetadata missing bucketName/outputObjectPrefix/customIdsInOrder',
      };
    }

    // List output files. Vertex writes them as predictions-XXXXX-of-YYYYY.jsonl
    // under outputObjectPrefix, sometimes inside a deeper subdirectory it
    // generates for the job. Filter for *.jsonl and sort lexically so shards
    // land in their numbered order.
    const storage = new Storage();
    const bucket = storage.bucket(bucketName);
    const [files] = await bucket.getFiles({ prefix: outputObjectPrefix });
    const predictionFiles = files
      .filter((f) => f.name.endsWith('.jsonl') && f.name.includes('prediction'))
      .sort((a, b) => a.name.localeCompare(b.name));

    if (predictionFiles.length === 0) {
      return { status: 'failed', error: `no prediction files under gs://${bucketName}/${outputObjectPrefix}` };
    }

    const results: BatchResultItem[] = [];
    let index = 0;
    let succeeded = 0;
    let failed = 0;
    for (const file of predictionFiles) {
      const [buf] = await file.download();
      const text = buf.toString('utf-8');
      for (const rawLine of text.split('\n')) {
        if (!rawLine.trim()) continue;
        const customId = customIdsInOrder[index] ?? `unknown-${index}`;
        index++;
        let parsed: {
          status?: string;
          request?: unknown;
          response?: GenerateContentResponse;
        };
        try {
          parsed = JSON.parse(rawLine);
        } catch {
          results.push({ customId, success: false, error: 'malformed output line' });
          failed++;
          continue;
        }

        // Vertex marks per-line errors by populating `status` with a non-empty
        // error string. SUCCEEDED lines have an empty/absent status.
        if (parsed.status && parsed.status !== '') {
          results.push({ customId, success: false, error: parsed.status });
          failed++;
          continue;
        }

        if (!parsed.response) {
          results.push({ customId, success: false, error: 'no response in output line' });
          failed++;
          continue;
        }

        const response = parsed.response as GenerateContentResponse;
        const textOut = extractTextFromGeminiResponse(response);
        let output: unknown;
        let outText: string | undefined;
        try {
          output = JSON.parse(textOut);
        } catch {
          outText = textOut;
        }
        results.push({
          customId,
          success: true,
          output,
          text: outText,
          usage: this.normalizeUsage(response, 0),
        });
        succeeded++;
      }
    }

    return {
      status: 'completed',
      results,
      requestCount: customIdsInOrder.length,
      completedCount: succeeded,
      failedCount: failed,
    };
  }
}

// ─── Shared helpers (also used by anthropic + openai adapters) ──────────────

/**
 * Flatten the OraclePromptPlan into a (systemPrompt, userMessage) pair.
 * Stable blocks become the system prompt; semi-stable / retrieved / dynamic
 * blocks concatenate into the user message in order. Preserves cacheable-
 * prefix ordering so provider-native cache machinery actually hits.
 */
export function flattenPlan(plan: OraclePromptPlan): {
  systemPrompt: string;
  userMessage: string;
} {
  const { systemPrompt, prefixContext, dynamicInput } = splitPlanForCaching(plan);
  return {
    systemPrompt,
    userMessage: [prefixContext, dynamicInput].filter(Boolean).join('\n\n'),
  };
}

/**
 * Convert a Zod schema (or any unknown — we duck-type) to standard JSON
 * Schema 2020-12. Falls back to assuming the input is already JSON Schema if
 * it doesn't look like a Zod object.
 */
export function zodToJsonSchema(schema: unknown): unknown {
  const s = schema as { _def?: unknown };
  if (s && typeof s === 'object' && '_def' in s) {
    return z.toJSONSchema(schema as ZodTypeAny);
  }
  return schema;
}

/**
 * Best-effort Zod runtime validation. Returns the validated value on success,
 * or null if the input doesn't look like a Zod schema (so the caller can fall
 * back to the raw parsed JSON). Throws on Zod validation failure — the caller
 * decides what to do.
 */
export function tryZodParse<T>(schema: unknown, value: unknown): T | null {
  const s = schema as { safeParse?: (v: unknown) => { success: boolean; data: T; error: unknown } };
  if (s && typeof s === 'object' && typeof s.safeParse === 'function') {
    const result = s.safeParse(value);
    if (!result.success) {
      throw new Error(
        `VertexGeminiAdapter.generateObject: model output failed Zod validation: ${String(result.error)}`,
      );
    }
    return result.data;
  }
  return null;
}

/**
 * Translate unified ReasoningEffort to Vertex Gemini 2.5+'s thinkingConfig.
 * Returns an object you can spread into the request `config`.
 *
 * Budgets (Gemini 2.5 Pro/Flash):
 *   off    → thinkingBudget: 0  (disables thinking)
 *   low    → 1024
 *   medium → 8192
 *   high   → 24576 (Flash hard cap; Pro accepts up to 32768)
 *
 * Models without thinking support (1.x family) ignore the param silently.
 */
function vertexThinkingConfig(effort: ReasoningEffort | undefined):
  | { thinkingConfig: { thinkingBudget: number } }
  | Record<string, never> {
  if (!effort) return {};
  const budget =
    effort === 'off' ? 0
      : effort === 'low' ? 1024
      : effort === 'medium' ? 8192
      : 24576;
  return { thinkingConfig: { thinkingBudget: budget } };
}

/**
 * Map @google/genai JobState onto our provider-agnostic BatchStatus.
 *
 *   JOB_STATE_QUEUED | _PENDING | _RUNNING | _UPDATING | _PAUSED → 'in_progress'
 *   JOB_STATE_SUCCEEDED                                          → 'completed'
 *   JOB_STATE_PARTIALLY_SUCCEEDED                                → 'completed'
 *   JOB_STATE_FAILED                                             → 'failed'
 *   JOB_STATE_EXPIRED                                            → 'expired'
 *   JOB_STATE_CANCELLING | _CANCELLED                            → 'canceled'
 */
function mapVertexBatchStatus(state: string): BatchStatus {
  switch (state) {
    case 'JOB_STATE_SUCCEEDED':
    case 'JOB_STATE_PARTIALLY_SUCCEEDED':
      return 'completed';
    case 'JOB_STATE_FAILED':
      return 'failed';
    case 'JOB_STATE_EXPIRED':
      return 'expired';
    case 'JOB_STATE_CANCELLING':
    case 'JOB_STATE_CANCELLED':
      return 'canceled';
    case 'JOB_STATE_QUEUED':
    case 'JOB_STATE_PENDING':
    case 'JOB_STATE_RUNNING':
    case 'JOB_STATE_UPDATING':
    case 'JOB_STATE_PAUSED':
      return 'in_progress';
    default:
      // Unknown / undocumented → assume still running so the drain task polls again
      return 'in_progress';
  }
}

/**
 * Pull the text from a GenerateContentResponse. The synchronous adapter relies
 * on `response.text` (a getter), but offline-deserialized response objects
 * from the batch output JSONL don't carry the getter — they're plain data.
 * Walk candidates[0].content.parts[] and concatenate the text parts.
 */
function extractTextFromGeminiResponse(response: GenerateContentResponse): string {
  // Use the SDK getter if it's present (won't be after JSON.parse).
  const direct = (response as { text?: string }).text;
  if (typeof direct === 'string' && direct.length > 0) return direct;
  const candidate = response.candidates?.[0];
  const parts = candidate?.content?.parts ?? [];
  const chunks: string[] = [];
  for (const part of parts) {
    const partText = (part as { text?: string }).text;
    if (typeof partText === 'string') chunks.push(partText);
  }
  return chunks.join('');
}
