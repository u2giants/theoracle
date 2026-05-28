/**
 * Provider adapter interface.
 *
 * Every provider-native adapter (Anthropic, Vertex Gemini, OpenAI) must
 * implement this interface. The OracleAIClient dispatches through it; no
 * route handler or worker may call the provider SDKs directly.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md "Core interfaces".
 */

import type {
  OraclePromptPlan,
  OracleTextResult,
  OracleObjectResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute, OracleProvider } from '../routes';

export interface GenerateObjectArgs<TSchema> {
  plan: OraclePromptPlan;
  route: OracleModelRoute;
  /** Zod schema (or compatible) that the output must satisfy. */
  schema: TSchema;
  /**
   * Optional generic escape hatch for cache-control hints and other
   * provider-specific knobs that don't belong on OraclePromptPlan.
   */
  providerOptions?: Record<string, unknown>;
}

export interface GenerateTextArgs {
  plan: OraclePromptPlan;
  route: OracleModelRoute;
  /**
   * Optional generic escape hatch for adapter-specific parameters that
   * don't fit into the OraclePromptPlan. The chat route uses this for:
   *   - `tools` (Vercel AI SDK ToolSet)
   *   - `stopWhen` (stepCountIs(N) for multi-turn tool calls)
   *   - `temperature`
   *   - `messages` — multi-turn conversation history that overrides the
   *     single (system, user-message) shape flattened from the plan
   *
   * Adapters that don't support a given option ignore it silently. The
   * shape is unconstrained on purpose to avoid leaking provider-specific
   * types into the OracleAIClient surface.
   */
  providerOptions?: Record<string, unknown>;
}

// ─── Batch API contract ─────────────────────────────────────────────────────
//
// Provider Batch APIs (OpenAI Batch, Vertex Batch Prediction, Anthropic
// Message Batches) run async at ~50% sync pricing with a 24-hour SLA. The
// adapter contract is intentionally provider-agnostic; provider-specific
// identifiers (OpenAI file IDs, Vertex GCS URIs) flow through the opaque
// `providerMetadata` field which the caller persists to
// `provider_batch_jobs.provider_metadata_json` and passes back at retrieve
// time. See DECISIONS.md D14.

export interface BatchRequest {
  /**
   * Caller-supplied identifier echoed back in `BatchResultItem.customId`.
   * The caller uses it to map results to its own per-input rows
   * (e.g. extraction_batches.id).
   */
  customId: string;
  plan: OraclePromptPlan;
  /** Provider-specific per-request options (rare; usually empty). */
  providerOptions?: Record<string, unknown>;
}

export interface SubmitBatchArgs {
  route: OracleModelRoute;
  requests: BatchRequest[];
  /**
   * Structured-output JSON Schema applied uniformly to every request.
   * Adapters translate per provider: Anthropic → forced tool call,
   * OpenAI → response_format json_schema strict, Vertex → responseJsonSchema.
   * If omitted, the batch is treated as generateText (free-form output).
   */
  jsonSchema?: unknown;
  /**
   * Provider-specific batch-level options. Examples:
   *  - OpenAI: { completionWindow?: '24h' }
   *  - Vertex: { inputGcsUri?, outputGcsUri? } (adapter generates if omitted)
   */
  providerOptions?: Record<string, unknown>;
}

export interface SubmitBatchResult {
  /** The provider's batch identifier. Used to poll status later. */
  providerBatchId: string;
  /**
   * Opaque provider-specific metadata. Persist verbatim and pass back at
   * retrieve time. Examples:
   *  - OpenAI: { inputFileId, outputFileId?, errorFileId? }
   *  - Vertex: { inputGcsUri, outputGcsUri }
   *  - Anthropic: {} (batch ID is sufficient)
   */
  providerMetadata: Record<string, unknown>;
}

export type BatchStatus =
  | 'submitted'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'expired'
  | 'canceled';

export interface BatchResultItem {
  /** Echoed from the original BatchRequest.customId. */
  customId: string;
  success: boolean;
  /** Set for generateText-style outputs (no jsonSchema). */
  text?: string;
  /** Set for generateObject-style outputs — parsed JSON (NOT yet Zod-validated). */
  output?: unknown;
  /** Provider-reported token usage for the individual request. */
  usage?: OracleUsage;
  /** Present when success === false. */
  error?: string;
}

export interface RetrieveBatchArgs {
  providerBatchId: string;
  /** The `providerMetadata` returned by submitBatch, persisted by the caller. */
  providerMetadata: Record<string, unknown>;
  route: OracleModelRoute;
}

export interface RetrieveBatchResult {
  status: BatchStatus;
  /** Populated when status is 'completed' (and optionally partial 'failed'). */
  results?: BatchResultItem[];
  /** Provider's reported counts when available. */
  requestCount?: number;
  completedCount?: number;
  failedCount?: number;
  /** Set when status is 'failed' / 'expired' / 'canceled' and there's a top-level cause. */
  error?: string;
}

export interface OracleProviderAdapter {
  readonly provider: OracleProvider;

  generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>>;

  generateText(args: GenerateTextArgs): Promise<OracleTextResult>;

  /** Optional — only adapters that natively support streaming implement this. */
  streamText?(args: GenerateTextArgs): AsyncIterable<{ delta: string; usage?: OracleUsage }>;

  /**
   * Optional — submit a batch of requests to the provider's Batch API.
   * Adapters that don't implement this aren't usable in batch mode; the
   * two-phase extraction worker falls back to sync for those providers.
   */
  submitBatch?(args: SubmitBatchArgs): Promise<SubmitBatchResult>;

  /** Optional — poll status and retrieve results once status === 'completed'. */
  retrieveBatch?(args: RetrieveBatchArgs): Promise<RetrieveBatchResult>;
}

/** True when the adapter implements the optional Batch API methods. */
export function supportsBatch(adapter: OracleProviderAdapter): boolean {
  return typeof adapter.submitBatch === 'function'
    && typeof adapter.retrieveBatch === 'function';
}

/**
 * Sentinel error thrown by stub adapters when their real implementation has
 * not yet been built. OracleAIClient may catch this and route to a fallback
 * adapter or to the mock adapter under test mode.
 */
export class ProviderAdapterNotImplementedError extends Error {
  constructor(public readonly provider: OracleProvider) {
    super(
      `Provider adapter for "${provider}" is not yet implemented. R2 ships the interface and stubs only; real SDK integration lands in R3+. Use OracleAIClient in test mode to exercise the call shape.`,
    );
    this.name = 'ProviderAdapterNotImplementedError';
  }
}
