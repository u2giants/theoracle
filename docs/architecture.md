# Architecture

System design for The Oracle. For business context and the operating philosophy, read `oracle_master_spec.md` Parts 1–2. For the developer-facing map, read `AGENTS.md`.

## Components

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              Identity providers                             │
│   Microsoft Entra (popcre tenant)      Google OAuth                         │
│   Supabase email magic-link  ← Brevo SMTP    Authentik OIDC (TODO)          │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ↓
                            Supabase Auth
                            (auth.users)
                                   ↓
                  packages/auth/src/link.ts (linker)
                                   ↓
            ┌──────────────────────┴──────────────────────┐
            ↓                                             ↓
   employee_identities                              employees
   (one row per employee × provider)               (authorization roster)
            │                                             │
            └─────────── joined via employee_id ──────────┘

┌──────────────────┐    ┌────────────────────────┐    ┌──────────────────────┐
│   apps/web       │    │   Supabase Postgres    │    │   apps/workers       │
│   Next.js 16     │◄──►│  + pgvector + RLS      │◄──►│   Trigger.dev v3     │
│   App Router     │    │                        │    │                      │
│   Vercel Fluid   │    │  Schema in             │    │  - claim extraction  │
│   Compute        │    │  packages/db/src/      │    │  - doc ingestion     │
│                  │    │  schema.ts             │    │  - contradiction     │
│  /channels/...   │    │                        │    │    watcher           │
│  /admin/...      │    │  RLS, constraints,     │    │  - brain synthesis   │
│  /api/chat       │    │  views, data migs in   │    │                      │
│  /auth/...       │    │  migrations/sql/*.sql  │    │  Each task writes    │
│                  │    │                        │    │  job_runs +          │
│                  │    │                        │    │  model_runs rows.    │
└────────┬─────────┘    └────────────────────────┘    └──────┬───────────────┘
         │                          ▲                        │
         │                          │                        │
         │                  ┌───────┴────────┐               │
         │                  │  Supabase      │               │
         │                  │  Storage       │               │
         │                  │  bucket:       │               │
         │                  │  company_documents             │
         │                  └────────────────┘               │
         │                                                   │
         │      ┌──────────────────────────────┐             │
         └─────►│  Supabase Realtime           │◄────────────┘
                │  - postgres_changes(messages)│
                │  - presence (typing)         │
                └──────────────────────────────┘
                            ↓
                  Browser chat UI
                  (channel-chat.tsx)

         ┌──────────────────────────────────────┐
         │           LLM providers              │
         │  Every model call goes through       │
         │  OracleAIClient → ModelRouter →      │
         │  one of six direct adapters          │
         │  (registered via buildStandardAdapters):
         │    AnthropicAdapter                  │
         │      (@anthropic-ai/sdk)             │
         │    VertexGeminiAdapter               │
         │      (@google/genai)                 │
         │    GoogleGeminiAdapter               │
         │      (@google/genai)                 │
         │    OpenAIAdapter                     │
         │      (openai)                        │
         │    DeepSeekAdapter                   │
         │      (openai SDK + api.deepseek.com) │
         │    QwenAdapter                       │
         │      (openai SDK + dashscope-us)     │
         │  Embeddings:                         │
         │    OpenAI text-embedding-3-small     │
         │    via packages/ai/src/embeddings.ts │
         │  See § "AI model adapters" below     │
         │  for the full per-provider table.    │
         └──────────────────────────────────────┘
                             ▲
                             │
                   packages/ai
                   Files: client/oracle-ai-client.ts,
                   context/context-compiler.ts,
                   routing/model-router.ts,
                   providers/{anthropic,vertex-gemini,
                   google-gemini,openai,mock}-adapter.ts,
                   routes/catalog.ts (curated routes),
                   embeddings.ts, retrieval.ts,
                   prompts/{oracle-system,extraction-system}.ts.
```

Every production model call goes through this pipeline. The Vercel AI SDK is explicitly forbidden in `packages/ai/src/providers/` per DECISIONS.md D6 + D9 — the adapters use the providers' official raw SDKs directly. OpenRouter is **never** used for inference (the legacy `getOpenRouter()` was retired in commit `b01e514` / R11.0). OpenRouter's `/v1/models` endpoint IS used by `packages/ai/src/model-capabilities/sources/openrouter.ts` to enrich the admin-side model catalog with pricing and capability flags — that's the only OpenRouter touchpoint left.

## AI model adapters

The adapters are the "translation layer" between Oracle's provider-agnostic call shape and each LLM provider's specific API. There are 6 production adapters today.

### The adapter contract

All adapters implement `OracleProviderAdapter` (`packages/ai/src/providers/types.ts`):

```typescript
interface OracleProviderAdapter {
  readonly provider: OracleProvider;     // 'anthropic' | 'vertex' | 'google' | 'openai' | 'deepseek' | 'qwen'
  generateText(args: GenerateTextArgs): Promise<OracleTextResult>;
  generateObject<TSchema, TOutput>(args: GenerateObjectArgs<TSchema>): Promise<OracleObjectResult<TOutput>>;
  streamText?(args: GenerateTextArgs): AsyncIterable<{ delta: string; usage?: OracleUsage }>;
}
```

Callers don't pick an adapter directly. They:

1. Read the per-stage setting (`default_${role}_route` + `default_${role}_reasoning_effort`) via `resolveRouteFromSettings(db, role)`.
2. Get back an `OracleModelRoute` with `provider`, `modelId`, `reasoningEffort`, and cache strategy attached.
3. Pass the route to `OracleAIClient.runText()` or `runObject()`.
4. `ModelRouter` looks up the adapter by `route.provider` and dispatches `generateText` or `generateObject` against it.
5. The adapter calls the provider SDK, normalizes the response into `OracleTextResult` / `OracleObjectResult`, and normalizes usage into `OracleUsage`.

`buildStandardAdapters()` in `packages/ai/src/client/standard-adapters.ts` returns the production adapter map (`{ anthropic, vertex, google, openai, deepseek, qwen }`). It's tolerant of missing env keys — an adapter whose constructor throws is silently omitted, so a missing `DEEPSEEK_API_KEY` only fails requests routed to DeepSeek, not the whole map. Every worker and the chat route import this helper rather than instantiating adapters individually.

### Per-adapter behavior

| Concern | AnthropicAdapter | OpenAIAdapter | VertexGeminiAdapter | GoogleGeminiAdapter | DeepSeekAdapter | QwenAdapter |
|---|---|---|---|---|---|---|
| SDK | `@anthropic-ai/sdk` | `openai` | `@google/genai` | `@google/genai` | `openai` (custom baseURL) | `openai` (custom baseURL) |
| Base URL | `api.anthropic.com` (SDK default) | `api.openai.com` (SDK default) | `<region>-aiplatform.googleapis.com` | `generativelanguage.googleapis.com` | `https://api.deepseek.com` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1` |
| Auth env var | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` (+ optional `OPENAI_ORG_ID`) | Application Default Credentials + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` | `GEMINI_API_KEY` or service-account OAuth from `GOOGLE_APPLICATION_CREDENTIALS_JSON` | `DEEPSEEK_API_KEY` | `DASHSCOPE_API_KEY` |
| `generateText` call | `client.messages.create({ model, max_tokens, system, messages, [thinking] })` | `client.chat.completions.create({ model, messages, [temperature], [reasoning_effort] })` | `client.models.generateContent({ model, contents, config: { systemInstruction, [thinkingConfig] } })` | `client.models.generateContent({ model, contents, config: { systemInstruction, [thinkingConfig.thinkingLevel] } })` | `client.chat.completions.create({ model, messages, [temperature] })` | `client.chat.completions.create({ model, messages, [temperature], [enable_thinking, thinking_budget] })` |
| `generateObject` strategy | Tool-call enforcement: a single tool named `output_structured` whose `input_schema` is the JSON Schema; `tool_choice: { type: 'tool', name: TOOL_NAME }` forces invocation. | Native `response_format: { type: 'json_schema', json_schema: { name, strict: true, schema } }` — provider enforces the schema. Refusals come back as a `refusal` field. | Native `responseMimeType: 'application/json'` + `responseJsonSchema` — accepts standard JSON Schema since `@google/genai` 2.6. | Same native Gemini JSON mode as Vertex, but through the Gemini API and API key auth. | `response_format: { type: 'json_object' }` + Zod validation pass. DeepSeek does NOT support strict json_schema mode; we embed the schema in the system prompt and validate after. | Same as DeepSeek (json_object + Zod). DashScope's OpenAI-compat exposes `json_object` but not strict json_schema. |
| Cache strategy | Explicit per-block `cache_control: { type: 'ephemeral', ttl }` markers on the stable system prompt and, for multi-turn chat, on the reusable conversation prefix immediately before the latest dynamic turn. | Automatic prefix caching plus per-request `prompt_cache_retention` selection (`in_memory` for active chat, `24h` for long-lived extraction/synthesis/admin workloads). Reads `usage.prompt_tokens_details.cached_tokens`. | Implicit caching remains on by default, and the adapter now also creates explicit `cachedContent` resources, persists them through `provider_cached_content`, reuses them across processes by `source_hash`, and can switch to file-backed cache inputs via temporary `gs://...` objects for oversized artifacts. The file-backed path serves both extraction (single-turn document corpus) and **interview chat** (a large attached PDF cached once as a `systemInstruction + fileData` prefix, with the multi-turn conversation sent as live contents on top — gated on `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` + a Vertex interview route). | DeepSeek auto-prefix caching. Hits in `usage.prompt_cache_hit_tokens`; the adapter relies on deterministic prefix shaping because the provider does not expose user-managed explicit cache handles. | Explicit prompt caching on DashScope Chat Completions via `cache_control` markers on the reusable prefix plus Responses-API session cache on the text path when a stable session key is supplied; `previous_response_id` is persisted per channel in `provider_response_sessions`. |
| Reasoning effort param | `thinking: { type: 'enabled', budget_tokens: N }` (N: low=2048, medium=8192, high=24000; clamped to `max_tokens - 512`). **Forces `temperature: 1`** because Anthropic rejects any other temp when thinking is on. | `reasoning_effort: 'low' \| 'medium' \| 'high'` (off omits the param). Silently ignored by non-reasoning models. | `thinkingConfig: { thinkingBudget: N }` (off=0, low=1024, medium=8192, high=24576). Ignored by Gemini 1.x. | None passed. R1 reasoning is automatic and not client-controlled; the adapter logs the requested effort for observability. | `enable_thinking` boolean + optional `thinking_budget`. off → `enable_thinking: false`. low/med/high → `enable_thinking: true` with budget 2048/8192/24576. Passed as top-level params (DashScope's OpenAI-compat forwards unknown keys). |
| Usage normalization (into `OracleUsage`) | `inputTokens` ← `usage.input_tokens`. `outputTokens` ← `usage.output_tokens`. `cachedInputTokens` ← `usage.cache_read_input_tokens`. `cacheWriteTokens` ← `usage.cache_creation_input_tokens`. | `inputTokens` ← `usage.prompt_tokens`. `outputTokens` ← `usage.completion_tokens`. `cachedInputTokens` ← `usage.prompt_tokens_details.cached_tokens`. `reasoningTokens` ← `usage.completion_tokens_details.reasoning_tokens`. | `inputTokens` ← `usageMetadata.promptTokenCount`. `outputTokens` ← `usageMetadata.candidatesTokenCount`. `cachedInputTokens` ← `usageMetadata.cachedContentTokenCount`. `reasoningTokens` ← `usageMetadata.thoughtsTokenCount`. | `inputTokens` ← `usage.prompt_tokens`. `outputTokens` ← `usage.completion_tokens`. `cachedInputTokens` ← `usage.prompt_cache_hit_tokens` (DeepSeek-specific, not the OpenAI shape). `reasoningTokens` ← `usage.completion_tokens_details.reasoning_tokens`. | Same shape as OpenAI normalization (DashScope OpenAI-compat returns the OpenAI usage shape). |
| Multi-turn messages | `providerOptions.messages` override (Vercel-AI-SDK-shaped `ChatCompletionMessageParam[]`). | Same. | Transforms the multi-turn array into Vertex's `contents` shape (text parts only today — inline image/file parts are not yet translated; chat routes large PDFs through the file-backed cache instead). On the file-cache path the full conversation is preserved as live contents on top of the cached prefix. | Same as OpenAI. | Same as OpenAI. |
| What it CAN'T do today | Streaming-with-tools end-to-end in this codebase; tool_use streaming requires explicit demuxing not yet wired. | Vision input wiring inside the adapter (chat route handles it outside the adapter via a regex — see AGENTS.md pending work). | Translate inline multimodal message parts (images / non-cached files) into Vertex `inlineData`/`fileData` — `buildContents` collapses each turn to a single text part, so inline images/PDFs on a Vertex chat route are not rendered. Large PDFs are handled via the file-backed cache; general multimodal-inline support is the prerequisite for caching alongside other inline attachments. | Strict json_schema (deepseek doesn't expose it). Streaming. | Strict json_schema. Streaming. The structured-output path still uses Chat Completions rather than Responses. |

### The end-to-end call shape

Take a chat-route call. The flow:

```
POST /api/chat
  ↓
apps/web/app/api/chat/route.ts
  • resolveRouteFromSettings(db, 'interview')
    → reads settings.default_interview_route ('anthropic_claude_haiku_4_5_interview_primary')
    → reads settings.default_interview_reasoning_effort ('medium')
    → returns OracleModelRoute { provider: 'anthropic', modelId: 'claude-haiku-4-5', reasoningEffort: 'medium', ... }
  • client = getOracleClient()   // lazy-init OracleAIClient with buildStandardAdapters()
  • result = await client.runText({ plan, route, providerOptions: { messages, temperature, cache } })
  ↓
OracleAIClient.runText()
  • compile()  → OraclePromptPlan { stableBlocks, dynamicBlocks, outputContract }
  • ModelRouter.resolve(route.routeId) → { route, adapter }   // adapter = AnthropicAdapter instance
  • adapter.generateText({ plan, route, providerOptions })
  ↓
AnthropicAdapter.generateText()
  • flattenPlan(plan) → { systemPrompt, userMessage }
  • thinking = thinkingParam(route.reasoningEffort, defaultMaxTokens)
    → 'medium' → { type: 'enabled', budget_tokens: 8192 }
  • client.messages.create({
      model: 'claude-haiku-4-5',
      max_tokens: 4096,
      temperature: 1,           // forced because thinking is on
      system: [{ type: 'text', text: systemPrompt, cache_control: { type: 'ephemeral' } }],
      messages: [...userMessage...],
      thinking
    })
  • normalizeUsage(response, latencyMs) → OracleUsage with input/output/cached/cacheWrite/reasoning tokens
  • return { text, usage, rawResponse }
  ↓
OracleAIClient.runText() returns { text, usage, plan, contextPackId }
  ↓
apps/web/app/api/chat/route.ts persists to oracle_context_packs + model_runs + model_run_usage_details
```

Failure modes are handled at the routing layer (auto-fallback if `route.fallbackRouteId` is set and the primary call throws a transient error), at the adapter layer (refusals / parse failures throw typed errors), and at the worker layer (the candidate-before-claim pipeline catches output-validation failures and triggers schema_repair).

### Batch API support (foundation landed 2026-05-28)

`OracleProviderAdapter` exposes two **optional** methods for async batch dispatch via provider Batch APIs (~50% off sync pricing, 24-hour SLA):

```typescript
submitBatch?(args: SubmitBatchArgs): Promise<SubmitBatchResult>;
retrieveBatch?(args: RetrieveBatchArgs): Promise<RetrieveBatchResult>;
```

The contract flows through provider-agnostic types in [packages/ai/src/providers/types.ts](packages/ai/src/providers/types.ts). Provider-specific shapes (OpenAI file IDs, Vertex GCS URIs) live inside the opaque `providerMetadata` field that the caller persists to `provider_batch_jobs.provider_metadata_json` and passes back at retrieve time.

| Provider | submitBatch / retrieveBatch | Infrastructure needed |
|---|---|---|
| `OpenAIAdapter` | ✅ landed — JSONL via `client.files.create` + `client.batches.create` against `/v1/chat/completions` | None — uses OpenAI's file API |
| `VertexGeminiAdapter` | ✅ landed — GCS-backed JSONL via `client.batches.create` with `src`/`dest` GCS URIs | `GOOGLE_VERTEX_BATCH_GCS_BUCKET` env var + `roles/storage.objectAdmin` for the SA |
| `AnthropicAdapter` | ✅ landed — Message Batches via `client.messages.batches.create` + `.results()` streaming JSONL. Forced single-tool call for structured output (mirrors `generateObject`). `providerMetadata` is `{}` — the batch ID alone is sufficient | None — Anthropic hosts the input + results |
| `DeepSeekAdapter` | n/a — no public Batch API |
| `QwenAdapter` | n/a — DashScope batch surface is non-OpenAI-compat; would require native DashScope SDK swap (D12 deferred) |

DB shape (migration `60_batch_jobs.sql`):
- `provider_batch_jobs` — one row per submitted batch. Status: `submitted | in_progress | completed | failed | expired | canceled`. Stores `provider_metadata_json` and `customIdsInOrder` (for Vertex, which doesn't echo per-request IDs).
- `extraction_batches.provider_batch_job_id` — nullable FK linking per-input rows to their owning batch job.
- `model_runs.dispatch_mode` — `'sync' | 'batch' | NULL` for cost dashboards.

Worker integration landed 2026-05-28. Three Trigger.dev tasks coordinate via the `extraction_dispatch_mode` setting:

| Task | Cron | Role |
|---|---|---|
| `claim-extraction` (sync) | `0 */4 * * *` | Bails when mode is `'batch'`. Otherwise the existing sync pipeline. |
| `claim-extraction-batch-submit` | `0 */4 * * *` | Bails when mode is `'sync'`. Otherwise: gather messages, build prompts, insert `extraction_batches` + `oracle_context_packs`, call `adapter.submitBatch`, persist `provider_batch_jobs` row, link the batches. |
| `claim-extraction-batch-drain` | `*/10 * * * *` | Always runs. Polls `provider_batch_jobs` WHERE status IN ('submitted', 'in_progress'); when completed, parses each result, inserts `model_runs` with `dispatch_mode='batch'`, then calls `processSegmentOutput` to run the SAME R5/R5.5 validators + promotion pipeline as the sync path. |

Sync and batch paths share `processSegmentOutput` (exported from `claim-extraction.ts`), so candidate-before-claim validation, taxonomy validation, sensitivity gating, and `executePromotion` behave identically regardless of which model dispatch the segment came from. Flip dispatch mode via the **Settings → Extraction dispatch mode** toggle on `/admin/settings` (DispatchModeToggle client component, posts to `/api/admin/settings`) or by direct SQL: `UPDATE settings SET value = '"batch"'::jsonb WHERE key = 'extraction_dispatch_mode';`. Read every cron tick, no redeploy needed.

### Adding a new provider

Adding a sixth provider (e.g. Mistral, xAI) is a contained change:

1. **Add the provider to the type union** — `packages/ai/src/routes/types.ts` → `OracleProvider`.
2. **Add the provider's prefix mapping** — `packages/ai/src/routes/resolve.ts` → `OR_PROVIDER_MAP` (so `mistralai/mixtral-8x22b` resolves to provider `mistral`). Without this, picking that model in the admin UI silently falls back to the default catalog route.
3. **Write the adapter** — `packages/ai/src/providers/<name>-adapter.ts` implementing `OracleProviderAdapter`. ~150–250 LOC; mirror the structure of an existing adapter (DeepSeek/Qwen are the smallest; OpenAI is the canonical reference). Define provider-native cache + reasoning translation in the file.
4. **Register the adapter** — `packages/ai/src/client/standard-adapters.ts` → add one `tryAdd(map, 'name', () => new XAdapter())`.
5. **Add a model-list source** — `packages/ai/src/model-capabilities/sources/<name>.ts` returning `RawProviderModel[]`. Update `refreshModelCatalog()` in `packages/ai/src/model-capabilities/index.ts` to call it.
6. **Add the cache strategy enum value** — `packages/ai/src/routes/types.ts` → `CacheStrategy`. Update `makeSyntheticRoute()` in `resolve.ts` to pick the new strategy.
7. **Relax the DB CHECK constraint** — `packages/db/migrations/sql/<NN>_model_capabilities_more_providers.sql`.
8. **Add the env var** — `.env.example` + `turbo.json` `globalEnv` + Vercel project + Trigger.dev project + `docs/configuration.md`.
9. **Update the UI provider labels** — `apps/web/app/admin/settings/model-pool/_components/model-pool-editor.tsx` → `PROVIDER_LABELS` + `PROVIDER_ORDER`.
10. **Document it here** — add a row to the per-adapter table above.

The DeepSeek+Qwen rollout (commit `c5cea1d`) added ~600 lines across ~17 files using exactly this checklist. Estimate ~half a day for a new provider with a well-behaved SDK; the only hard parts are the provider-specific quirks (system prompt placement, structured output mode, native tool-calling schema, cache lifecycle), which are unavoidable regardless of architecture.

## Teams transcript ingestion (Microsoft Graph)

Pulls Microsoft Teams **call transcripts** into the same evidence pipeline as chat and documents. POP's meetings are all ad-hoc "Meet Now" calls, never scheduled — which constrains the design (see below). Status: **LIVE + validated end-to-end** for post-call transcript ingestion (2026-06-04/05).

```
Teams call (transcription ON)
  ↓  Microsoft publishes a transcript after the call ends
Microsoft Graph change-notification subscription
  resource: communications/adhocCalls/getAllTranscripts  (BETA only; v1.0 rejects it)
  ↓  POST (encrypted) to notificationUrl
apps/web/app/api/teams/notifications/route.ts   (the "always-on listener", on Vercel)
  • validation handshake (echo ?validationToken — Graph checks this at create time)
  • verify clientState, decrypt the rich payload (graph-notification-crypto.ts:
    RSA-OAEP unwrap → HMAC-SHA256 verify → AES-256-CBC decrypt)
  • triggerTask('teams-transcript-ingestion', { transcriptContentUrl, meetingId, ... })
  ↓
apps/workers/src/trigger/teams-transcript-ingestion.ts
  • fetch the WebVTT (graph-transcripts.ts:fetchTranscriptVtt)
  • parseVtt → mergeBySpeaker → one utterance per turn
  • resolve speaker → employee by display-name (null when unmatched)
  • INSERT a channel (per call) + channel_participants + messages
    (role='user', extraction_status='pending', clientMessageId='teams:<transcriptId>:<n>')
  ↓
existing claim-extraction cron picks up the pending messages  →  candidate-before-claim
```

Each utterance becomes a `messages` row (not a `document_chunk`) precisely so it carries speaker attribution (`employeeId`) and verbatim quotes — the same evidence shape as chat. Idempotent: re-running for the same transcript is a no-op (the `clientMessageId` dedupe key). Nothing here writes to `claims` — the normal R5/R6 validators run downstream.

Subscription lifecycle is owned by `teams-subscription-manager.ts`: the `teams-subscription-renew` cron (`*/30`) and a webhook-lifecycle-triggered task both call the idempotent `ensureAdhocSubscription()` (renew if <20 min left, else create). The resource max-lifetime is ~1h, so a machine must keep re-upping it — no human re-authenticates anything.

**Hard constraints (derived from Microsoft Graph, not choices):**
- **Ad-hoc calls are only reachable via a subscription, and only on beta.** `getAllTranscripts(meetingOrganizerUserId=...)` (used by `diagnose-transcripts.ps1`) enumerates *scheduled* meetings only; ad-hoc "Meet Now" calls never appear there. The subscription is "listen going forward" — a transcript only notifies if the subscription existed *before* transcription started; past calls are unrecoverable.
- **No Graph live transcript / no Graph live spoken awareness.** Graph exposes no API to read a meeting's live caption/transcript stream, and Teams does not pipe spoken words into the meeting text chat. The Graph path therefore ingests calls *after* they end. Live spoken participation is a separate Recall.ai meeting-bot path, not a Graph capability.
- **The webhook must be deployed before the subscription can be created** — Graph validates `notificationUrl` synchronously at create time.

The Graph subscription/transcript surface is intentionally duplicated: `apps/web/lib/microsoft-graph.ts` (web/webhook side) and `apps/workers/src/lib/graph-transcripts.ts` (worker side), because apps/web and apps/workers are separate processes and cross-app imports aren't allowed. The web copy is the reference. See AGENTS.md §10.

**Status: LIVE + validated end-to-end (2026-06-04/05).** Real call → 95 speaker-attributed messages → claims. Refinements made while validating on real data:

- **Speaker resolution is email-based.** VTT display name → M365 directory email (Graph `/users`) → employee by `employees.email` or `employee_identities.email`; an unmatched `@popcre.com` speaker bootstraps a provisional employee. (`employees.name` often differs from the transcript display name, so name-matching alone failed.)
- **Quote validation is fuzzy on the message/transcript path** (`validateQuote` `allowFuzzy`), strict on documents — spoken transcripts are paraphrased, so verbatim matching rejected nearly everything. Deterministic token-overlap; evidence anchored to the real utterance. See AGENTS.md §10 and DECISIONS.md D-transcript-fuzzy-quote.
- **Raw VTT is persisted** in `raw_transcripts` (hand-written `migrations/sql/62_raw_transcripts.sql`) at ingestion, so the pipeline is re-runnable from true source after Microsoft expires the transcript.
- **`TRIGGER_SECRET_KEY` in Vercel must be the prod key** or webhook-triggered ingestion lands in the dev env and expires (AGENTS.md §13, 2026-06-04).

A separate **live** capture path also exists (`bfd6612`): a Recall.ai bot joins the call for real-time STT (`apps/web/app/api/teams/{live,bot}/*`, worker `teams-live-recall-utterance.ts`), externalizing the media layer that Graph and the no-VPS posture rule out. Live utterances enter the same candidate-before-claim pipeline as `messages`. See DECISIONS.md.

## Teams live participation (Recall.ai)

Adds live Teams meeting awareness without changing the Vercel/Supabase/Trigger.dev infrastructure. Recall.ai owns the meeting bot and audio/STT transport; The Oracle receives finalized transcript utterances and decides whether to ask a short meeting-chat question.

Status: **LIVE + validated end-to-end (2026-06-08/09).** The tested path is: admin start route -> Recall Teams bot join -> ElevenLabs/AssemblyAI live STT -> signed `/api/teams/live/recall` webhook -> Trigger.dev `teams-live-recall-utterance` -> `messages` persistence -> Recall `send_chat_message` -> visible Teams chat post. The latest tested worker deployment is `20260609.6` after removing the temporary test-only bot-create task.

After the live test, posting was deliberately clamped off in `settings` (`max_oracle_interjections_per_hour=0`, `teams_live_recall_min_confidence_to_post=101`, force flags false). The live decision is retrieval-backed (prompt version `teams-live-recall-1.1.0`): before the interjection decision, the worker runs the one endorsed claim-retrieval path (`buildRetrievalPlanFromQuery` → `searchWithRetrievalPlan`, top 5) over the current utterance plus recent meeting context, enriches the results with evidence and linked Brain snippets, and injects that approved knowledge as a `retrieved_context` prompt block. The worker writes an `oracle_context_packs` row before the model call, links it to `model_runs` / `model_run_usage_details`, and records actual fallback metadata from the AI result. The model reports which claim IDs influenced its decision; the worker validates them against the retrieved set and stores `retrievedClaimIds` + `evidenceClaimIds` in the interjection assistant-message `metadata_json` and the job output. Retrieval failures degrade to the no-context prompt — they never block the utterance path. The live Oracle still only asks clarification questions; it never answers the meeting, and claim IDs never appear in the Teams chat text.

```
Admin POST /api/teams/live/start { meetingUrl, provider }
  provider: elevenlabs_streaming first, assembly_ai_v3_streaming fallback
  ↓
apps/web/lib/recall.ts creates Recall bot with realtime_endpoints=[/api/teams/live/recall]
  ↓
Recall bot joins Teams meeting, transcribes speech live
  ↓ finalized transcript.data event (not partials)
apps/web/app/api/teams/live/recall/route.ts
  • verify Recall whsec_ signature
  • triggerTask('teams-live-recall-utterance', { event })
  ↓
apps/workers/src/trigger/teams-live-recall-utterance.ts
  • normalize utterance words -> text
  • create/find per-bot Oracle channel
  • resolve speaker by email/name when available
  • insert messages row: role='user', source='teams_live_recall'
  • keyword gate skips low-signal utterances
  • rate/cooldown gates via oracle_interventions
  • retrieval plan over the utterance -> top approved claims (searchWithRetrievalPlan)
  • interview-route LLM decides whether to ask one short question, given the
    retrieved approved-knowledge block + recent utterance window
  • evidence claim IDs stored on the assistant message metadata_json
  • Recall send_chat_message posts the question to Teams chat
```

This path uses finalized utterances only. STT partials are provisional hypotheses while someone is still speaking; acting on them would make Oracle interrupt on half-heard sentences. Post-call Graph transcripts remain the canonical backstop for complete evidence if live bot delivery drops events.

### Teams-native command wrapper

The Recall listener itself cannot be invited from the Teams people picker as an internal employee. To let employees initiate it from Teams, The Oracle also exposes a Bot Framework endpoint:

```
Teams user adds The Oracle app to a meeting/chat
  ↓
@The Oracle join <Teams meeting link>
  ↓
Azure Bot Service -> /api/teams/bot/messages
  • verifies Bot Framework auth via MICROSOFT_BOT_APP_ID/PASSWORD
  • strips the @mention and parses join/listen/start commands
  • uses Teams meeting context for joinUrl when available
  • otherwise asks the user to include the meeting link
  • creates the Recall live bot
```

So the user-facing flow originates inside Teams, while the live audio/STT work is still performed by Recall.

Current production wiring (2026-06-09): Azure Bot resource `theoracle-popcre-teams-bot` routes the Microsoft Teams channel to `https://oracle.designflow.app/api/teams/bot/messages`; the Teams organization app `The Oracle` is uploaded with app id `17ccd7a1-b90b-428c-9966-33e7fb832923`. This does not replace Recall.ai for live audio/STT; it only provides the native Teams command surface.

## Identity model

One human → one `employees` row → many `employee_identities` rows.

- `employees.email` is the **primary contact** for the human (used for display, admin contact, and first-login bootstrap).
- `employee_identities` is the authoritative source for `(auth_provider, auth_user_id)`. Supabase Auth identifies the user; the linker maps that Supabase user to the employee row through this table.
- The linker resolves a session by `(auth_provider, auth_user_id)` first. On miss it bootstraps by matching the verified provider email against `employees.email` OR any existing `employee_identities.email` row, then creates a new identity. See `packages/auth/src/link.ts`.
- The RLS helper `current_employee_id()` joins `employees` with `employee_identities` on `auth.uid()` — RLS does not read `employees.auth_user_id` directly.
- Deprecated columns `employees.auth_user_id`, `employees.auth_provider`, `employees.auth_provider_subject` remain on the schema as NULL placeholders during the multi-identity transition. They will be dropped in a follow-up migration. See `DECISIONS.md` D2.multi-identity.
- `employees.departments text[]` (multi-value, authoritative) replaces `employees.department varchar` (single-value, nullable, deprecated). All new code reads `departments`; legacy code falls back to `department`. The retrieval layer uses `departments` as `departmentHints` — a soft RRF signal, never a hard filter.

## Data flow — the load-bearing paths

### 1. Employee sends a message

1. Browser inserts into `messages` via the Supabase client (RLS enforced — must be a participant of the channel).
2. Supabase Realtime fan-outs `postgres_changes` to other participants.
3. If the message starts with `@oracle` (or `oracle,`), the client calls `POST /api/chat` (see flow 2).
4. The message row sits with `extraction_status='pending'`. The claim extraction worker (Phase 4) picks it up later.

### 2. `@oracle` mention → chat response

1. `POST /api/chat` receives `{ channelId }`. The employee is resolved server-side from the Supabase session cookie — the client does not pass an employee ID.
2. The route resolves the requester's `employees` row through `employee_identities` (matches `auth.uid()` from the Supabase session). Verifies the requester is a participant of `channelId`.
3. Classifies the query via `buildRetrievalPlanFromQuery` (heuristic keyword → `topDomainHints`, `requiredEntities`, `excludedDocumentClasses`, `searchScope`). Passes the employee's `departments` array as `departmentHints` — a soft signal added to the RRF score (+0.002 per claim whose `claim_metadata.department` matches). Runs hybrid pgvector + tsvector RRF via `searchWithRetrievalPlan` with metadata pre-filter. Also fetches recent N messages, employee profile, and top open gaps for this employee/department.
4. Builds prompt blocks with the spec Part 10 system prompt plus the deterministic retrieval bundle. Multi-turn `messages`, `temperature`, provider cache hints, and optional Qwen session handles are passed through `providerOptions`; Vercel AI SDK tool definitions are not used by the direct adapters.
5. Calls `OracleAIClient.runText`. Route is `settings.default_interview_route` (default `anthropic_claude_haiku_4_5_interview_primary`) and may fall back through `ModelRouter`.
6. On completion: inserts the assistant message into `messages`, writes `model_runs` + `model_run_usage_details`, and uses the AI result metadata to record the actual dispatched route plus any fallback origin/reason.

### 3. Document upload

Two entry points, both ending in the same `document-ingestion` worker:

- **Admin → Documents** (company/process docs): `POST /api/admin/documents` (admin-only, multi-file, **no channel**). Stores each file to `company_documents`, inserts a `documents` row (`status='pending_processing'`) with optional uploader `context` + `domain_hints`, and triggers `document-ingestion`. This is the path for seeding company knowledge — there is no UI to create a chat channel.
- **Channel attachment** (chat): `POST /api/documents` requires a channel; it additionally inserts an `extraction_status='skipped'` attachment message and a `message_attachments` row, then triggers `POST /api/chat` (DMs always; group chats only when the caption starts with `@oracle`).

The `document-ingestion` worker then:

1. Loads the `documents` row and parses by format (`resolveParseKind`, matching MIME or filename extension): **PDF** (`pdf-parse`), **Word .docx** (`mammoth`), **Excel/CSV** (`xlsx`), **plain text/markdown/vtt**, and **images** (PNG/JPEG/WebP/HEIC).
2. **Images run a two-pass flow:** Pass 1 (`transcribeImageToText`) sends the image to the admin-selected vision model (`default_vision_route`; default Gemini, provider-direct) and gets back a faithful text rendering — a structured text topology for diagrams (nodes `[Shape: "label"]`, edges `[A] --(cond)--> [B]`, swimlane headers), verbatim labels kept inside the nodes. That text is the substrate for Pass 2.
3. Chunks the text into persisted `document_chunks`, using paragraph-aware chunking before falling back to character windows, then embeds them. Existing uploaded rows keep whatever chunks they already have; re-upload or deliberately recreate chunks to apply new chunking behavior.
4. Runs claim extraction over one or more labeled chunk windows via the extraction route. Each window is bounded for model reliability, but the worker should cover every persisted chunk; there is no silent "first N characters only" document cap. The prompt includes `DOCUMENT CHUNK` blocks and their `document_chunks.id` values, so document-derived candidates use a chunk ID as `sourceMessageId`. The uploader `context` is injected into the extraction prompt (and the Pass-1 vision prompt); `domain_hints` are a non-binding prior — per-claim `domain_valid` stays authoritative.
5. Promotes claims through the candidate-before-claim executor. Every claim's `exactQuote` must appear inside one persisted `document_chunk`; for text/Markdown documents the validator applies deterministic Markdown formatting normalization before matching, and for images the source text is the transcription. Quotes that span chunks are rejected rather than patched into claims.

Failures are written to `documents.processing_error`. Admin → Documents shows a plain-English status summary with expandable technical details so a user can see what happened while a developer or AI session can diagnose the exact worker/provider error. A retry clears stale `processing_error` when processing starts and again on success.

Unknown-only entity taxonomy results are allowed to promote while staging entity proposals; invalid domains, ambiguous domains, and entity type mismatches still block promotion. This lets new business-process docs seed real claims before the entity registry is fully populated without weakening the domain/evidence gates.

### 4. Claim extraction (worker — deployed, Phase 4)

Cron: every 4 hours (`0 */4 * * *`). Also triggered by document ingestion.

1. Queries `messages WHERE extraction_status='pending' AND role='user'`. Batches up to 100 messages per run.
2. Groups by channel, then splits into 60-minute conversation segments.
3. Calls `OracleAIClient.runObject` with the curated extraction route (`settings.default_extraction_route`, default `vertex_gemini_2_5_flash_extraction_primary`), dispatched through the direct `VertexGeminiAdapter` (`@google/genai`) with native `responseJsonSchema` structured-output mode.
4. Validates exact quotes against the source text verbatim — invalid quotes are rejected without inserting.
5. Inserts `claims` + `claim_top_domains` + `claim_evidence` rows via the R5 candidate-before-claim promotion executor. Auto-approves low-risk claim types with impact ≤ 6; others go to `pending_review`. (Legacy `claim_domains` is no longer written; backfilled rows remain in the table for historical reads only.)
6. Suggests `gaps` rows for unanswered questions.
7. Marks source messages `extraction_status = 'complete'`, `'failed'`, or `'skipped'`. Writes `job_runs` + `model_runs` rows.

### 5. Synthesis (worker — deployed, Phase 4)

Cron: weekly (Mondays 06:00). Also admin-triggerable.

1. Reads up to 200 approved claims per brain section via `claim_top_domains`. The read scope is the union of the section's `knowledgeDomain` and its `relatedDomains` jsonb array, each legacy value mapped through `mapLegacyDomainToTopDomain`. `sectionClaims` is queried separately for explicitly-bound claims.
2. Routes through `OracleAIClient.runObject` using the curated route from `settings.default_synthesis_route` (default `anthropic_claude_3_5_sonnet_synthesis_primary`). Dispatched through the direct `AnthropicAdapter` (`@anthropic-ai/sdk`) with forced tool-call structured output.
3. `validateSynthesisDiff` rejects the run if (a) any material paragraph cites a non-approved claim ID, OR (b) the markdown mentions a capitalized proper-noun-shaped name not backed by an approved claim summary or the canonical entity registry. See `packages/oracle-engines/src/synthesis/diff-validator.ts`.
4. On success: inserts a new `brain_section_versions` row (`reviewStatus='draft'` or `'needs_review'`) and updates `brain_sections.current_version_id` (two-step transaction per spec 6.7).
5. On rejection: inserts a `brain_section_versions` row with `reviewStatus='rejected'` carrying the failed markdown + `validationFailures` + `unsupportedNames` in `structuredContent`. `currentVersionId` is NOT updated — the failed output is preserved for admin review without changing the current Brain version.

### 6. Admin review (Phase 5 — done)

Four server-component dashboards under `/admin/`:

- `/admin/claims` — pending-review queue with lateral join to primary evidence, asserting employee, and `claim_top_domains` domain chips. Approve/Reject/Revise server actions (`_actions.ts`) are audited in `claim_review_events`. Revise creates a replacement claim, copies evidence/domain/entity metadata, marks the original `superseded`, and links `claim_metadata.superseded_by_claim_id`.
- `/claims` — non-admin domain-review queue. A user can review a claim when they belong to a department mapped to at least one of the claim's top domains through `knowledge_domain_review_departments`; admins can review all claims.
- `/admin/gaps` — Drizzle query joined with employees. Priority + status badges. Resolve/Stale server actions.
- `/admin/contradictions` — raw SQL via the `contradictions` table joined with both claim summaries (mirrors `contradictions_with_claim_summaries` view). Card-per-row layout. Confirm (possible→open) / Dismiss server actions.
- `/admin/brain` — `brain_sections` LEFT JOIN `brain_section_versions` on `current_version_id`. Scrollable markdown preview, review-status badge. Read-only; re-synthesis trigger is post-retrofit.

All four read via `getDirectDb()` (service role) and use `'use server'` actions with `revalidatePath` rather than client-side state.

### 7. Interjection engine (Phase 6 / R11 — done)

Both paths from spec Part 5.1 are live:

- **Lull-driven** — `apps/workers/src/trigger/lull-interjection.ts` (R11.2). Cron `* * * * *`. Per active channel: query `secondsSinceLastUserMessage`, `minutesSinceLastOracleInterjection`, count of interventions in last hour, top open gap whose target is null or a channel participant. Call `decideLullInterjection` (pure, in `packages/oracle-engines/src/interjection.ts`). On `'ask'`: draft the natural-language question via `OracleAIClient.runText` on the interview route (Anthropic Claude Haiku 4.5), insert the assistant message into `messages`, record `oracle_interventions` with `trigger_type='lull_gap'` + `was_live_interjection=true` + `interjection_message_id` + `related_gap_id`, update the gap `status='asked'` + `askedInMessageId`.

- **Contradiction-driven** — `apps/workers/src/trigger/contradiction-watcher.ts` (R11.0 + R11.3 + retrieval enforcement). Per-claim and sweep-cron tasks build a `RetrievalPlan` via `buildDomainScopedPlan` (when the claim has `claim_top_domains` rows) or `buildGlobalRetrievalPlan` (with a structured warning when domain tags are absent), then call `searchWithRetrievalPlan` for ANN. Semantic pairs are adjudicated via `OracleAIClient.runObject` on the extraction route (Vertex Gemini Flash). For each detected contradiction: resolve the most-recent message-sourced channel from `claim_evidence → messages`, compute cooldown + rate-cap inputs for that channel, call `decideContradictionInterjection`. On `'live'`: draft a chat-shaped surfacing question via the interview route (Anthropic Haiku 4.5) and post it; the `oracle_interventions` row carries the real `channelId` + `interjection_message_id` + `was_live_interjection=true`. On `'queue'` (or live drafting failure): create a `contradiction_gap` so the question still gets asked through the normal gap pipeline.

Both paths log every decision (skip / queue / ask / live) to `oracle_interventions` with the stable `reasonCode` from the pure deciders, so admin can audit miss rates and tune the settings:

- `lull_window_seconds` (default 60)
- `oracle_cooldown_minutes` (default 10)
- `max_oracle_interjections_per_hour` (default 3)
- `enable_group_chat_lull_questions` (default true)
- `enable_live_contradiction_interjections` (default true after R11; was false pre-R11)
- `CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD` (constant, default 80 — adjust in code for next-phase tuning)

Round-1 simplifications in `lull-interjection.ts` (per `DECISIONS.md` D11):

- `isAnyoneTyping` hardcoded to `false`. Real Supabase Realtime presence query is round 2.
- Top relevant gap chosen by priority + channel-participation, not by embedding similarity to recent messages. Topical-relevance scoring is round 2.

See spec Part 5.1, `DECISIONS.md` D10 + D11, and `docs/oracle/05-ai-retrofit-phase-packet.md` "Phase R11".

### 7. Sign-out

`POST /auth/signout` clears the Supabase session cookies server-side (via the same `@supabase/ssr` cookie adapter the callback uses) and redirects to `/`. The button is a `<form action="/auth/signout" method="post">` — POST avoids accidental sign-outs from URL prefetchers, and clearing cookies server-side avoids the "client says signed out but SSR pages still think they're signed in" gap.

## Major constraints

- **Postgres is the only source of truth.** No Redis, no file-based memory, no in-process AI memory. Every durable bit of state lives in a row.
- **Traceability is the product.** Every claim links to ≥1 `claim_evidence` row. Worker validators enforce exact-quote integrity.
- **No containers, no VPS.** Vercel + Supabase + Trigger.dev. Spec Part 2.5.
- **RLS first, application authorization second.** Browser code uses the anon key + RLS. Server routes use the service-role key only where it's documented and necessary.
- **Identity is durable through `employee_identities`** — emails on `employees` can change, but the `(provider, auth_user_id)` tuples in `employee_identities` are the stable identifiers.
- **Embeddings dimension is 1536** and locked. Changing it requires re-embedding everything. See AGENTS.md §11.
- **Supabase Postgres connection is via the poolers**, never the direct `db.*.supabase.co` hostname (IPv6-only on new projects). See AGENTS.md §11 + `docs/configuration.md`.

## Module dependency graph

```
packages/shared
   ↑   ↑       ↑
   │   │       │
packages/db ──→ packages/auth
   ↑   ↑           ↑
   │   │           │
packages/ai ───────┘
   ↑
   │
packages/oracle-engines
   ↑
   │
apps/web ───────────────→ apps/workers
   (no app-to-app deps; both depend on packages)
```

- `packages/shared` has zero internal deps.
- `packages/db` depends on `shared`.
- `packages/auth` depends on `db` + `shared`.
- `packages/ai` depends on `db` + `shared`.
- `packages/oracle-engines` depends on `db` + `shared`.
- `apps/web` depends on all packages.
- `apps/workers` depends on `db`, `shared`, `ai`.

Workers must not import from `apps/web`, and vice versa.

## Where each spec part is implemented

| Spec part | Implemented in |
|---|---|
| Part 4 (auth) | `packages/auth/`, `apps/web/app/auth/callback/route.ts`, `apps/web/app/auth/signout/route.ts`, `apps/web/app/denied/` |
| Part 4 (multi-identity extension) | `packages/db/src/schema.ts` (employee_identities), `packages/db/migrations/sql/15_employee_identities.sql`, `packages/auth/src/link.ts` |
| Part 5.1 (interjection) | `packages/oracle-engines/src/interjection.ts` (scaffold) |
| Part 5.2 (curiosity / gaps) | `packages/db/src/schema.ts` (`gaps` table) + `apps/workers/src/trigger/claim-extraction.ts` (inserts gap suggestions) |
| Part 5.3 (ingestion) | `apps/workers/src/trigger/document-ingestion.ts` (deployed) |
| Part 5.4 (synthesis) | `apps/workers/src/trigger/brain-synthesis.ts` (deployed) |
| Part 6 (schema) | `packages/db/src/schema.ts` |
| Part 6.8 (CHECK constraints) | `packages/db/migrations/sql/10_check_constraints.sql` |
| Part 6.9 (vector indexes) | `packages/db/migrations/sql/99_vector_indexes.sql` |
| Part 7 (RLS) | `packages/db/migrations/sql/20_rls_helpers.sql`, `21_rls_policies.sql` |
| Part 8 (admin views) | `packages/db/migrations/sql/30_admin_views.sql` |
| Part 9.1 (chat route) | `apps/web/app/api/chat/route.ts` + `packages/ai/src/retrieval.ts` |
| Part 9.2 (retrieval context) | `apps/web/app/api/chat/route.ts` + `packages/ai/src/retrieval.ts` |
| Part 9.4 (claim extraction) | `apps/workers/src/trigger/claim-extraction.ts` (deployed) |
| Part 10 (system prompt) | `packages/ai/src/prompts/oracle-system.ts` (verbatim) |
| Settings / model config | `apps/web/app/admin/settings/model-pool` — per-stage pool checkbox table (Interview / Extraction / Synthesis columns) backed by the persisted `model_capabilities` Postgres table. **Stage requirements:** `apps/web/lib/stage-requirements.ts` is the shared source of truth for the pool page and the settings picker. Interview requires tools + structured output + vision + context >100K. Extraction requires structured output + context >100K, intentionally **not** vision because uploaded images are transcribed by the auxiliary Image Vision model before extraction receives text. Synthesis requires context >400K + structured output + reasoning + output-cap support. **Model discovery:** each of the 5 provider APIs is called in parallel (`sources/anthropic.ts` → Anthropic `/v1/models`, `sources/openai.ts` → OpenAI `/v1/models`, `sources/google.ts` → Google Gemini `/v1beta/models`, `sources/deepseek.ts`, `sources/qwen.ts`). **OpenAI filtering:** the OpenAI source uses a blocklist of non-chat categories (audio, image, realtime, TTS, transcription, moderation, video, legacy completion) rather than an allowlist of chat prefixes — new GPT/o-series generations pass through automatically. **Post-enrichment quality filters (all 5 providers):** (1) models with no pricing AND no capability flags are dropped; (2) models priced ≥ $15.01/1M input tokens are dropped. Pricing and capability flags come from OpenRouter (`sources/openrouter.ts` → `openrouter.ai/api/v1/models`, joined by model id with dash→dot + date-stripping normalization). All sources are fetched in parallel; per-source failures are non-fatal and surfaced in `errors[]`. **Defense in depth:** the same filter is applied again in `/api/admin/model-catalog` GET (`passesQualityFilter`) so rows already in the DB from before the write-time filter shipped are never returned to the admin UI. Existing DB rows are preserved (deprecated models may still be referenced by pool selections) — they're just filtered at read time. `/api/admin/model-catalog`: GET reads the table (filtered), POST triggers a full refresh (also filtered); `model-catalog-refresh-nightly` in Trigger.dev runs the same refresh every night at `15 7 * * *`. `/api/admin/models?stage=<>`: returns the per-stage pool (`settings.model_pool_<stage>`) or full catalog if pool is empty; auxiliary ids such as `vision` and `general` bypass stage pools and return the full catalog for auxiliary filtering. Workers resolve their route via `resolveModelRoute(modelIdOrRouteId, role)` in `packages/ai/src/routes/resolve.ts`, which accepts both catalog `routeId`s and `provider/model` strings. Three role-setting keys (`default_interview_route`, `default_extraction_route`, `default_synthesis_route`) feed the pipeline callers; auxiliary route settings such as `default_vision_route` are resolved through `resolveAuxiliaryRouteFromSettings`. |
| Phase 5 admin review dashboards | `apps/web/app/admin/{claims,gaps,contradictions,brain}/page.tsx` + `_actions.ts`. Server actions; no client-state library. |

### Intentionally awkward — flag these before assuming they're bugs

- **`brain_sections.current_version_id` has no FK to `brain_section_versions`.** Looks like a missing constraint; it's a soft reference because the two tables reference each other circularly. Inserts happen as a two-step transaction (insert section with null, insert first version, update section). Documented in AGENTS.md §11 and `oracle_master_spec.md` Part 6.7.
- **`claims` has no `employee_id` column.** Looks like a schema oversight; it's intentional. A claim can be supported by multiple employees, documents, or external systems across time. Attribution lives on `claim_evidence.asserted_by_employee_id` per row.
- **Deprecated columns on `employees` (`auth_user_id`, `auth_provider`, `auth_provider_subject`) are NULL-filled and still present.** Looks like dead columns; they're kept during the multi-identity transition because dropping them mid-session would force a column-drop migration. Removal is in AGENTS.md §15 pending work. New code must read identities through `employee_identities`, not these columns.
- **`packages/ai/src/openrouter.ts` and `apps/web/app/api/admin/models/route.ts` are absent on purpose.** Looks like missing files; they were deleted in commit `b01e514` (R11.0). OpenRouter is no longer part of the production AI path. Do not re-introduce them.
- **There is exactly one endorsed claim-retrieval path: `searchWithRetrievalPlan()`.** The chat route, Recall live worker, and contradiction-watcher all use it. The chat route performs retrieval deterministically before the model call; it does not rely on Vercel AI SDK tool definitions passed through `providerOptions`, because the direct provider adapters do not execute those tools. The legacy `searchApprovedClaims()` wrapper was deleted in this session (it had zero runtime callers; `@oracle/ai` is workspace-internal so there was no external-consumer reason to keep a deprecated export). Do not reintroduce a second retrieval path.
- **Embeddings fall back to a deterministic zero vector when `OPENAI_API_KEY` is unset.** Looks like a silent bug. It is intentional so local dev works without a real key; vector similarity is meaningless in that state but the schema and shape are preserved. AGENTS.md §11.

---

## AI architecture retrofit — COMPLETE (landed 2026-05-26)

R0 → R11.4 are all done. Every production AI call goes through `OracleAIClient` with one of six direct adapters (`AnthropicAdapter` / `VertexGeminiAdapter` / `GoogleGeminiAdapter` / `OpenAIAdapter` / `DeepSeekAdapter` / `QwenAdapter`) using the providers' raw SDKs or their official OpenAI-compatible surfaces. OpenRouter has been removed entirely from the inference path. The wet-test passed end-to-end against the live Supabase project (first real `claims` rows landed 2026-05-26 17:35 UTC). Both proactive interjection paths (R11.2 lull + R11.3 live contradiction) post live chat messages by default, gated by the pure decision functions in `packages/oracle-engines/src/interjection.ts`.

The work that remains is operational, not architectural. See `AGENTS.md` § 15 "Pending work" for the open task list (general-purpose route wiring, vision-detection regex replacement, periodic catalog-refresh cron, key rotation, deferred round-2 items). `DECISIONS.md` D6 + D9 record why the Vercel AI SDK and OpenRouter were ruled out; D10 + D11 record the live-interjection switch and the lull-interjection round-1 simplifications; D12 records the DeepSeek + Qwen addition and the chosen API surfaces.

### Runtime pipeline (R2, landed)

```
                     Next.js route / Trigger.dev worker
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  OracleAIClient  │  packages/ai/src/client/
                         └────────┬─────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
        ┌──────────────────┐            ┌────────────────────┐
        │ ContextCompiler  │            │   ModelRouter      │  packages/ai/src/routing/
        │ packages/ai/src/ │            │                    │
        │ context/         │            │  - resolve routeId │
        │                  │            │  - dispatch        │
        │ stable → semi    │            │  - fallback on     │
        │  → retrieved →   │            │    429 / timeout / │
        │  dynamic         │            │    NotImplemented  │
        │                  │            │  - attach actual   │
        │                  │            │    route metadata  │
        │                  │            └──────────┬─────────┘
        │ throws if stable │                       │
        │ appears after    │            ┌──────────┴──────────┬──────────────┐
        │ dynamic          │            ▼                     ▼              ▼
        └──────────────────┘    Anthropic adapter    Vertex Gemini      OpenAI adapter
                                    (stub)            adapter (stub)        (stub)
                                                                                │
                                                       (real SDK wiring in R3+)│
                                                                                ▼
                                                                 UsageNormalizer →
                                                                 model_run_usage_details
```

**Test mode** auto-registers `MockProviderAdapter` instances for all three providers, so the full pipeline runs without API keys. The smoke gate (`pnpm --filter @oracle/ai verify:r2`) covers 16 assertions including stable-before-dynamic ordering, generateText across all 3 provider shapes, Zod-validated `generateObject`, ModelRouter fallback dispatch, and `EvidenceValidator` accept/reject behavior.

**Validation layer:**

- `packages/ai/src/validation/structured-output-validator.ts` — Zod schema check, returns a discriminated `ValidationResult<T>` so the caller can decide whether to escalate to a repair route.
- `packages/ai/src/validation/evidence-validator.ts` — deterministic `.includes()` + offset verification with ambiguity guard (multi-occurrence quotes without offsets are flagged `ambiguous`, not silently accepted).

### Curated route catalog (R1, landed)

`packages/ai/src/routes/` defines `OracleModelRoute` and the 9 curated routes. Each of the 3 production roles has **exactly 1 Primary + 1 Fallback** — no balanced alternates or competing defaults.

| Role | Primary | Fallback |
|---|---|---|
| Interview | `anthropic_claude_haiku_4_5_interview_primary` | `openai_gpt4o_interview_fallback` |
| Extraction | `vertex_gemini_2_5_flash_extraction_primary` | `openai_gpt4o_mini_extraction_fallback` |
| Synthesis | `anthropic_claude_3_5_sonnet_synthesis_primary` | `vertex_gemini_2_5_flash_synthesis_fallback` |

Internal escalation subroutes (Flash-Lite triage, Haiku warmth escalation, GPT-4o-mini schema repair) live inside `OracleAIClient` and are not exposed in admin settings.

### Observability schema (R3, landed)

Three Drizzle tables (created by migration `0001_hot_johnny_blaze.sql`) feed the future cost/cache dashboards:

| Table | Purpose |
|---|---|
| `oracle_context_packs` | Full `OraclePromptPlan` per AI call. Block list, prompt/schema versions, cache-key hashes (`stable_prefix_hash`, `dynamic_input_hash`, etc.), retrieval plan, included record IDs. `model_run_id` is nullable so the pack can be created BEFORE the model run. |
| `model_run_usage_details` | 1:1 child of `model_runs` (UNIQUE on `model_run_id`). Adds the OracleUsage shape: `cached_input_tokens`, `cache_write_tokens`, `reasoning_tokens`, `provider_request_id`, raw provider usage JSON, plus fallback dispatch tracking (`fell_back_from_route_id`, `fallback_reason`). |
| `provider_cached_content` | Explicit Vertex cache tracking. Required reuse policy fields: `expected_reuse_count`, `latest_planned_reuse_step`, `hard_expiration_at`, `cleanup_owner`. `provider_metadata_json` stores provider-specific cleanup state such as temporary uploaded GCS object names. `status` ∈ `(active, deleted, expired, failed, orphaned)`; CHECK constraint enforces `deleted_at IS NULL iff status='active'`. |
| `provider_response_sessions` | Provider-native conversation/session state such as Qwen Responses `previous_response_id`, persisted by `(provider, session_key)` so session cache survives across requests and processes. |

The `model_runs_with_usage` view (`migrations/sql/31_observability_views.sql`) joins all three for dashboard queries and computes `cache_hit_ratio = cached_input_tokens / input_tokens`.

### Three-layer knowledge taxonomy (R3.5, landed)

15 tables installing the segmentation from `docs/oracle/07-knowledge-segmentation.md`:

```
Layer 1   knowledge_top_domains            15 domains seeded; admin-curated
            ↑                                each carries boundary rules:
            │                                belongs_here, does_not_belong_here,
            │                                common_entity_hints,
            │                                default_excluded_document_classes,
            │                                neighboring_domain_ids
            │
   ┌────────┴────────────────────────────────────┐
   │                                              │
   ▼                                              ▼
Layer 2   knowledge_sub_topics            (Tagging joins)
            empty on install              claim_top_domains, document_top_domains,
            centroid vector(1536)         document_chunk_top_domains,
            HNSW index                    message_top_domains, claim_sub_topics
                                          → retrieval scopes BEFORE claims exist

Layer 3   entities                        61 entities seeded
            ↑                                customers (5)   licensors (5; first-class)
            │                                systems (17)    departments (8)
            │                                geographies (4) process_stages (14)
            │                                document_classes (10)
            │
   ┌────────┴────────────────────────────────────┐
   │                                              │
   ▼                                              ▼
Tag joins  claim_entities,                claim_metadata
           document_chunk_entities,         process_stage, department, geography,
           message_entities                 document_class, effective_from,
                                            effective_until, superseded_by_claim_id

Governance taxonomy_proposals           Compact admin proposal cards
           taxonomy_change_log          Audit log of accepted changes
           entity_proposals             Unknown-entity queue
                                        Auto-mutation prohibited
```

The legacy `claim_domains` table and `knowledge_domain` Postgres enum are intentionally preserved during transition. `migrations/sql/42_claim_top_domains_backfill.sql` copies existing claim-domain rows into the new `claim_top_domains` join via an explicit mapping (e.g. `coldlion → it_systems`, `sampling → product_development`).

`design_file_operations` is a deliberately separate top-level domain for designer file hygiene: safe filenames, invalid characters, server/folder organization, Photoshop/Illustrator/InDesign file bloat, linked assets, packaging, versioning, archive cleanup, and handoff file practices. It is neighboring to `creative_design`, `product_development`, `production_lifecycle`, and `it_systems`, but it is not the same knowledge base. Questions about product/design approval status, customer revisions, or a SKU moving through the design/product workflow should stay in `product_development`, `creative_design`, `licensing_approvals`, or `production_lifecycle`; pure file-management questions should route to `design_file_operations` and avoid workflow domains unless explicitly requested.

`business_process` is the cross-functional domain for end-to-end company workflows, operating-model overviews, and handoffs that span multiple departments. It is not a generic dumping ground: specific claims should still carry narrower domains such as `licensing_approvals`, `product_development`, `production_lifecycle`, `customer_ops`, `logistics_shipping`, or `finance_pricing` when those domains are materially involved. Broad process queries expand across `business_process` and neighboring process domains so a question about the overall company workflow can retrieve both overview claims and department-specific process facts.

`finance_pricing` means product costing/pricing, not company finance/accounting. It is for costing sheets, SKU cost build-up, customer product pricing, margin assumptions, factory quote inputs, and costing handoffs. A costing sheet created by Design and sent to factories should usually also carry narrower workflow domains such as `creative_design`, `product_development`, `supply_chain`, or `production_lifecycle` when those parts of the handoff are materially involved.

Claim revision recalculates top-domain tags from the revised claim text. Reviewers do not manually select domains during revision; the server action runs the retrieval-plan domain classifier over the revised claim and writes the recalculated `claim_top_domains` rows to the replacement claim. If the classifier cannot infer any domain, it falls back to the original claim domains and records that method in `claim_review_events.ai_comparison_json`. Reviewer notes are audit/commentary in `claim_review_events`, not claim evidence; they should not be fed to Brain synthesis as source support unless a separate explicit evidence action is added.

Approved revisions now feed a correction-lesson loop for future extraction. `packages/ai/src/prompts/claim-correction-lessons.ts` reads `claim_review_events` where `action='revise'` and the replacement claim is `approved`, formats a compact semi-stable prompt block, and the message extraction, batch submit, and document ingestion workers include that block after the stable extraction system prompt. This is not fine-tuning; it is retrieval-like prompt guidance derived from reviewed claim pairs. Admins can inspect the exact lesson block at `/admin/ai/claim-lessons`.

`/admin/ai/extraction-ab` is a non-promoting A/B/C review surface for those same approved revisions. It compares the existing Gemini 2.5-era claim, a fresh `google/gemini-3.1-flash-lite` extraction, a fresh `qwen/qwen3.7-max` extraction, and the human revision. Reviewers score only the AI outputs; the human revision is the reference answer, not a scoreable variant. These eval outputs are never inserted into `claims`; they are only for choosing better extraction models/prompts.

### Gemini 3.1 eval route uses Google API, not Vertex

What changed:
`google_gemini_3_1_flash_lite_extraction_eval` dispatches through `GoogleGeminiAdapter` (`provider: 'google'`) even though other Gemini production routes still use `VertexGeminiAdapter`.

Why:
The production Vertex project/region returned `NOT_FOUND` for `gemini-3.1-flash-lite`, while the same deployed service-account credentials can call `gemini-3.1-flash-lite` through the Gemini API OAuth path. A live smoke test on 2026-06-15 returned valid structured JSON from `gemini-3.1-flash-lite`.

Future sessions should:
Do not remap `google/*` settings back to `vertex` unless Vertex access for the exact model and region has been verified. Keep `GEMINI_API_KEY` optional; `GoogleGeminiAdapter` can use `GOOGLE_APPLICATION_CREDENTIALS_JSON` to mint Gemini API OAuth tokens.

`operations_systems` is the dedicated domain for operational business-system workflows: ERP, CRM, PLM, spreadsheet-to-system migration, source-of-truth rules, field mapping, validation, and integration handoffs. The initial anchor workflow is moving OrderList, MasterData, and TaskList data from Google Sheets into Designflow PLM. It neighbors `it_systems`, `product_development`, `production_lifecycle`, `customer_ops`, and `finance_pricing`, but should not be used for generic account troubleshooting or broad IT administration unless the query is about business data flow.

`training_enablement` is the domain for teaching employees how to do their jobs: onboarding plans, role-specific training checklists, SOP learning paths, shadowing, cross-training, skill checks, and refresher training after workflow changes. It neighbors `people_org`, `it_systems`, `operations_systems`, `product_development`, `production_lifecycle`, and `customer_ops`, but is not an HR/personnel-record domain. Questions about who owns a workflow or who reports to whom stay in `people_org`; questions about compensation, discipline, performance evaluation, and personal conflicts should not route here.

Knowledge domains are now associated with departments for claim review through `knowledge_domain_review_departments`. This is an authorization map, not a retrieval signal: retrieval still uses `claim_top_domains`, entity tags, metadata, and employee department hints. Department members can approve, reject, or revise claims in mapped domains without full admin access; the action boundary re-checks the claim's domains before mutating anything.

### Candidate-before-claim staging (R4, landed)

The extraction pipeline runs through 4 new tables (`migrations/0003_magenta_lionheart.sql`):

```
model output
  → extraction_batches              circuit-breaker fields:
                                      validation_attempt_count,
                                      consecutive_quote_failure_count,
                                      model_run_ids_attempted,
                                      route_ids_attempted
  → extraction_candidates           sensitivity flags first-class:
                                      contains_sensitive_personal_data,
                                      contains_sensitive_hr_data,
                                      is_personal_conflict
                                    proposed_entities + proposed_metadata
                                    dedup pointers: duplicate_of_candidate_id,
                                      duplicate_of_claim_id
  → extraction_candidate_evidence   stores both model-provided AND validator-
                                    confirmed quote/offsets
  → extraction_validation_results   one row per deterministic check
  → (R5) transactional promotion    advisory-lock → claims +
                                    claim_top_domains + claim_evidence
```

13 CHECK constraints (in `migrations/sql/13_extraction_constraints.sql`) enforce the pipeline invariants that schema alone can't — `promoted-consistency`, `sensitive-consistency`, `validated-fields-required-on-pass`, source-type/pointer consistency, etc.

### Extraction pipeline pure logic (R5 + R5.5, landed)

`packages/oracle-engines/src/extraction/` ships the deterministic logic that workers compose. Every function in this list is pure (no DB, no API keys, no network) and covered by a smoke gate:

| Module | Function | Purpose |
|---|---|---|
| `quote-validator.ts` | `validateQuote` | Verbatim provenance check. Returns `exact_match` / `normalized_match` / `ambiguous` / `failed`. Supplied offsets are ground truth — they must decode to the exact quote or the row fails with `quote_offsets_match`. |
| `quote-validator.ts` | `validateSourcePointer` | Mirrors the `extraction_candidate_evidence_source_check` CHECK constraint. Fails fast before the DB insert. |
| `normalization.ts` | `normalize`, `methodForApplied` | CRLF / smart-quote / whitespace-collapse / trim. All OFF by default. Reports which normalizations actually changed the input so audits can replay the decision. |
| `candidate-hash.ts` | `computeCandidateHash`, `canonicalizeSummary` | Deterministic sha256 over canonicalized candidate (lowercased + collapsed-whitespace summary; sorted top-domain IDs; sorted validated quotes; sorted source pointers). Stable across order, case, and whitespace. |
| `promote-candidate.ts` | `decidePromotion` | Pure decider returning `insert_new_claim` / `append_to_existing_claim` / `reject(reason)`. Extended in R5.5 with `entityAssignments`, `metadata`, `entityProposalsToStage`. |
| `entity-resolver.ts` | `resolveEntity` | Alias → canonical lookup. Returns `resolved` / `unknown` / `type_mismatch` / `ambiguous`. Type-mismatch catches "Disney as vendor" — Disney is a `licensor` in the seed; the resolver refuses to silently create a vendor row. |
| `taxonomy-validator.ts` | `validateTaxonomy` | Validates every proposed top-domain against `knowledge_top_domains` + every proposed entity against the registry. Surfaces `entityProposalsToCreate` for unknown / type-mismatch entities. |
| `circuit-breaker.ts` | `decideCircuitBreaker` | 3-strike rule per `docs/oracle/03-candidate-before-claim-validation.md`. Returns `continue` / `allow_repair_pass` / `trip_breaker`. |
| `domain-mapping.ts` | `mapLegacyDomainsToTopDomains` | Transitional legacy `KNOWLEDGE_DOMAINS` → `TOP_LEVEL_DOMAINS` mapping. Mirrors `migrations/sql/42_claim_top_domains_backfill.sql` exactly. |
| `cache-profitability.ts` | `decideCacheProfitability`, `estimateTokensForCache` | Vertex explicit-cache heuristic. Returns `create_explicit_cache(rule)` / `skip_explicit_cache(reason)`. |

Run each smoke gate any time: `pnpm --filter @oracle/engines verify:r5` (33/33), `verify:r5.5` (45/45), `verify:r6` (30/30), `verify:r7` (19/19). Combined with R2 (16/16), 143 deterministic assertions cover the business logic.

### DB-aware extraction executor (R6 + R7, landed)

`packages/oracle-engines/src/extraction/promotion-executor.ts` is the only path that inserts into permanent `claims` / `claim_top_domains` / `claim_entities` / `claim_metadata` / `claim_evidence`. The transaction shape:

```
db.transaction(async (tx) => {
  // 1. Advisory lock — refuses to block; throws AdvisoryLockBusyError if taken.
  await tx.execute(sql`SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))`)

  // 2. RACE-SAFE re-read of candidate row + validated evidence INSIDE the lock.
  //    Caller passes only candidateId — the executor SELECTs the latest
  //    committed state. Pure mappers (mapCandidateRowToSnapshotCandidate,
  //    mapEvidenceRowToValidatedEvidence) convert DB rows into the snapshot
  //    shape decidePromotion consumes. Both mappers are unit-tested under
  //    R5 smoke cases M1–M10.
  const fresh = await loadCandidateSnapshotInLock(tx, candidateId)

  // 3. Missing candidate? Return invalid_state WITHOUT writing
  //    extraction_validation_results (FK target doesn't exist). The only
  //    reject branch that skips the audit row.
  if (!fresh.candidate) return { outcome: 'recorded_rejection', appliedDecision: { kind: 'reject', reason: 'invalid_state', ... } }

  // 4. Race-safe hash lookup INSIDE the lock. Partial UNIQUE on
  //    claims.candidate_hash means at most one row matches.
  const existing = await tx.select(...).from(claims).where(eq(claims.candidateHash, hash))

  // 5. Decide. The decider sees:
  //    - fresh candidate (latest committed status — promoted? validation_failed?)
  //    - fresh validated evidence (includes anything appended since caller's read)
  //    - in-lock existing-claim-by-hash lookup
  //    - caller's auxiliaryInputs.taxonomy + auxiliaryInputs.metadata
  //      (NOT race-protected against registry drift — see scope note below)
  const decision = decidePromotion({
    candidateHash, candidate: fresh.candidate, validatedEvidence: fresh.validatedEvidence,
    taxonomy: input.auxiliaryInputs?.taxonomy, metadata: input.auxiliaryInputs?.metadata,
    existingClaimWithSameHash: existing[0] ?? null
  })

  // 6. Stage entity_proposals (useful regardless of branch).
  // 7. Branch on decision.kind:
  //    insert_new_claim          → claims (with candidate_hash) + claim_top_domains
  //                                + claim_entities + claim_metadata + claim_evidence
  //                                + candidate.status='promoted'
  //                                + extraction_validation_results pass
  //    append_to_existing_claim  → claim_entities + claim_evidence appended
  //                                + candidate.status='duplicate' (current candidate
  //                                  is still validated; some OTHER candidate already
  //                                  committed a claim with the same hash)
  //                                + extraction_validation_results pass
  //    reject                    → candidate.status updated per reason
  //                                + extraction_validation_results fail
  //                                  (EXCEPT: invalid_state with missing candidate
  //                                   skips the audit row — see step 3)
})
```

**Two race scenarios — distinct branches:**

- *Same candidate, re-read inside the lock, status no longer `validated`* → `reject(already_promoted)` (if another worker promoted *this* candidate) or `reject(not_validated)` (if a sensitivity gate fired between reads).
- *Different candidate, same canonicalized hash* → `append_to_existing_claim`. The current candidate is still `validated`; a parallel extraction of the same operational fact already committed a claim with the same hash. Our validated evidence is appended to their claim and our candidate is marked `duplicate`.

**Scope of what's race-protected:** the candidate row + validated evidence + same-hash claim lookup. The caller-provided `auxiliaryInputs.taxonomy` and `auxiliaryInputs.metadata` are NOT — registry drift between caller-side `validateTaxonomy()` and executor promotion is tolerated. Taxonomy mutations happen via admin approval at `/admin/taxonomy` (minutes/hours scale), not worker activity (ms scale). See `DECISIONS.md` D8.taxonomy-stays-caller-provided for the rationale.

Cache lifecycle (`packages/oracle-engines/src/extraction/cache-lifecycle.ts`):
- `recordCacheCreation` inserts a `provider_cached_content` row with `status='active'` and the required reuse policy fields (`expected_reuse_count`, `latest_planned_reuse_step`, `hard_expiration_at`, `cleanup_owner`).
- `recordCacheReuse(handle)` bumps `actual_reuse_count`.
- `recordCacheTermination({ handle, status, reason })` marks the row `deleted | expired | failed | orphaned` and stamps `deleted_at`. The CHECK constraint on `provider_cached_content` enforces `deleted_at IS NOT NULL` whenever status is non-active.

### Worker and chat-route integration (R6 + R7 + R8 + R9 + R11.0, all landed)

Every production AI caller now dispatches through `OracleAIClient` with the six direct provider adapters:

| Caller | Phase | Status |
|---|---|---|
| `apps/workers/src/trigger/claim-extraction.ts` | R6 + R-providers | ✅ direct Vertex (extraction) / Anthropic (interview) / OpenAI (fallback) |
| `apps/workers/src/trigger/document-ingestion.ts` | R7 + R-providers | ✅ direct adapters |
| `apps/web/app/api/chat/route.ts` | R8 + R-providers | ✅ direct adapters + deterministic retrieval before the model call + `providerOptions` escape hatch for multi-turn/temperature |
| `apps/workers/src/trigger/brain-synthesis.ts` | R9 + R-providers | ✅ direct adapters + `validateSynthesisDiff` |
| `apps/workers/src/trigger/contradiction-watcher.ts` | R11.0 | ✅ direct adapters; observability rows on parity with the other workers |
| `apps/workers/src/trigger/taxonomy-reevaluation.ts` | R10.5 | ✅ k-means clustering + LLM cluster naming + `taxonomy_proposals` writing; domains below the 30-claim activation threshold are skipped |

Each caller follows the same pattern:
1. Build `OracleAIClient` with `buildStandardAdapters()` so every configured provider tag (`anthropic`, `vertex`, `google`, `openai`, `deepseek`, `qwen`) is registered through one source of truth.
2. Resolve the curated route from `settings.default_*_route` (R1 keys).
3. Compile a prompt plan with `ContextCompiler` (stable_system + dynamic content).
4. Insert `oracle_context_packs` row BEFORE the model call so its ID can thread through.
5. Call `OracleAIClient.runText` (chat) or `runObject` (workers). The result may carry `routeId`, `provider`, `modelId`, `fellBackFromRouteId`, and `fallbackReason` from `ModelRouter`.
6. Insert `model_runs` + `model_run_usage_details` + back-link the context pack. Use the result route/provider/model metadata for the actual dispatched route; use the pre-resolved route only as a fallback when metadata is absent.
7. Workers: stage `extraction_batches` + `extraction_candidates` + `extraction_candidate_evidence`, run validators, call `executePromotion`. Chat: persist the assistant message.

### Direct adapters (R-providers, landed)

Six production adapters in `packages/ai/src/providers/`:

| Adapter | SDK | Native features used |
|---|---|---|
| `AnthropicAdapter` | `@anthropic-ai/sdk` (v0.98+) | Per-block `cache_control: { type: 'ephemeral', ttl }` markers on stable system blocks and reusable multi-turn prefixes; forced tool-call structured output via `tools` + `tool_choice: { type: 'tool', name }`; `cache_read_input_tokens` + `cache_creation_input_tokens` normalized into `OracleUsage` |
| `VertexGeminiAdapter` | `@google/genai` (v2.6+) | `responseMimeType: 'application/json'` + `responseJsonSchema` for strict native JSON-schema output; implicit prefix caching plus explicit `client.caches.create(...)` / `cachedContent` reuse persisted through `provider_cached_content`; structured-output calls can cache stable + semi-stable + retrieved context while sending only dynamic input live; `usageMetadata.cachedContentTokenCount` + `thoughtsTokenCount` normalized into `OracleUsage` |
| `GoogleGeminiAdapter` | `@google/genai` (v2.6+) | Gemini Developer API path for `google/*` routes; `responseMimeType: 'application/json'` + `responseJsonSchema`; Gemini 3 `thinkingConfig.thinkingLevel`; useful when cataloged Gemini API models are not available to the configured Vertex project/region |
| `OpenAIAdapter` | `openai` (v6.39+) | `response_format: { type: 'json_schema', strict: true }`; auto-cache via `prompt_tokens_details.cached_tokens`; per-request `prompt_cache_retention`; reasoning tokens via `completion_tokens_details.reasoning_tokens` |
| `DeepSeekAdapter` | `openai` (custom baseURL to `api.deepseek.com`) | Automatic disk-backed prefix caching only; `prompt_cache_hit_tokens` normalized into `OracleUsage.cachedInputTokens`; no user-managed explicit cache resource exists today |
| `QwenAdapter` | `openai` (custom baseURL to DashScope OpenAI-compat) | Explicit prompt caching on Chat Completions via `cache_control` markers on reusable prefixes plus Responses-API session cache for text calls; `prompt_tokens_details.cached_tokens` / `cache_creation_input_tokens` and Responses cached-token usage normalized into `OracleUsage` |

Each adapter authenticates via env vars / ADC (see `docs/configuration.md`). The Vercel AI SDK is explicitly forbidden inside these adapters per DECISIONS.md D6 + D9 — it normalizes provider-specific cache fields and structured-output strategies through a uniform abstraction that destroys both. Raw SDKs preserve every native feature.

Structured-output adapters should parse JSON defensively (`parseJsonOrRaw`) and let `OracleAIClient` / Zod return `validation.ok=false` for schema mismatches whenever possible. Provider/network failures should still throw, but invalid model JSON should not bypass the validation result path.

### Synthesis pipeline (R9, landed)

`packages/oracle-engines/src/synthesis/` ships the deterministic synthesis-diff validator. The synthesis worker composes it with the OracleAIClient bridge pattern:

```
brain_sections + approved claims + entity registry
  ↓
ContextCompiler.compile()
  ├── stable_system block: ORACLE_SYSTEM_PROMPT + approved claim corpus
  └── dynamic_input block: per-trigger request
  ↓
oracle_context_packs row (modelRunId nullable, set after the call)
  ↓
OracleAIClient.runObject(SynthesisOutputSchema)
  via direct VertexGeminiAdapter / AnthropicAdapter / OpenAIAdapter
  ↓
model_runs + model_run_usage_details + back-link to context pack
  ↓
validateSynthesisDiff({
  output, approvedClaimIds, approvedClaimSummariesLower,
  registryEntityCanonicalsLower, expectedSectionId
})
  ↓
  ok=true  → brain_section_versions row (status='draft' or 'needs_review')
              + UPDATE brain_sections.currentVersionId
              + sectionClaims membership
              + newGaps insert + resolvedGaps update
  ok=false → brain_section_versions row (reviewStatus='rejected')
              with validationFailures + unsupportedNames in
              structuredContent. currentVersionId is NOT updated.
```

The seven failure kinds `validateSynthesisDiff` distinguishes:

| Failure kind | Trigger |
|---|---|
| `wrong_section_id` | `output.sectionId` doesn't match the requested section |
| `paragraph_cites_non_approved_claim` | `paragraphs[].supportingClaimIds` contains an ID not in the approved set |
| `material_change_cites_non_approved_claim` | `materialChanges[].claimId` not approved |
| `claim_ref_not_approved` | `claimsAdded` / `claimsStrengthened` / `claimsWeakened` references not approved (`claimsRemoved` is NOT checked — removed claims may no longer be approved by design) |
| `contradiction_cites_non_approved_claim` | `newContradictions[]` references claims not approved |
| `gap_missing_required_fields` | `newGaps[]` has empty `questionToAsk` or `whyItMatters` |
| `unsupported_named_entity` | A capitalized proper-noun-shaped name in `updatedMarkdown` is not backed by an approved claim summary OR the canonical entity registry |

The unsupported-named-entity check is the R9-new addition. It strips Markdown structure (code blocks, inline code, image refs, markdown links, ENTIRE heading lines) before regex-matching for capitalized proper-noun phrases, then checks each candidate against the lowercase approved-summary corpus and the lowercase registry canonical set. Heuristic, not a parser; false positives hold for admin review (acceptable), false negatives let fabricated names through (worse), so the stopword list is curated tight.

### Admin observability surface (R10, landed)

Six read-only Next.js App Router pages under `/admin/ai`. Server-rendered Drizzle queries against existing R3 / R4 / R7 tables and the `model_runs_with_usage` view. No new schema, no new server actions, no new dependencies.

| Route | Purpose | Reads from |
|---|---|---|
| `/admin/ai` | Top-level dashboard: 12 metric cards + route usage breakdown + recent runs | `model_runs_with_usage`, `provider_cached_content`, `extraction_candidates` |
| `/admin/ai/runs` | Paginated runs list (50/page, 4 filters + task-type chips) | `model_runs_with_usage` |
| `/admin/ai/runs/[id]` | One-run detail: summary, usage breakdown, full prompt-plan block list, retrieval diagnostics, linked extraction batches, linked provider caches | `model_runs_with_usage`, `oracle_context_packs`, `extraction_batches`, `provider_cached_content` |
| `/admin/ai/cache` | Cache rows filterable by status + provider hit-ratio, task/route efficiency, and high-cost low-hit tables | `provider_cached_content`, `model_runs_with_usage` |
| `/admin/ai/candidates` | Extraction candidate review with 8 filter tabs. Sensitive rows are excluded at the SQL level from every tab except the explicit "Sensitive" tab. | `extraction_candidates`, `extraction_validation_results` |
| `/admin/ai/evals` | Placeholder. Documents the CLI smoke gates. | — |

The sensitive-candidate exclusion is structural: the SQL `WHERE` clause prevents any UI toggle from leaking sensitive material into the standard queue.

### Taxonomy governance surface (R10.5, landed)

Five admin pages under `/admin/taxonomy` plus four transactional server actions plus a scheduled re-evaluation worker.

| Route | Purpose |
|---|---|
| `/admin/taxonomy` | Top-level domains list with full boundary rules + usage counts |
| `/admin/taxonomy/proposals` | Taxonomy proposals review queue with approve/reject |
| `/admin/taxonomy/entities` | Entity registry grouped by type (licensor split from vendor explicitly) |
| `/admin/taxonomy/entity-proposals` | Unknown-entity review queue. Approval can refine canonical + auto-merges on conflict |
| `/admin/taxonomy/change-log` | Append-only audit (latest 200 events) |

Server actions in `apps/web/app/admin/taxonomy/_actions.ts`:

- `approveTaxonomyProposal(id, reviewNote?)` — transactional. Applies the mutation INLINE for `create_top_domain` proposals (INSERT into `knowledge_top_domains` with full boundary rules). For `merge_top_domains` / `split_top_domain` / `reassign_claims` / `create_sub_topic` / `merge_sub_topics` / `split_sub_topic` / `retire_sub_topic` the proposal is marked approved with a `taxonomy_change_log` entry of `changeType='approve_pending_reclassification_<type>'`; the actual reclassification work is queued for the dedicated reclassification job (R10.5 task 4) which lands when those proposal types start arriving.
- `rejectTaxonomyProposal(id, reason)` — transactional reject + change-log audit.
- `approveEntityProposal(id, finalCanonicalValue?, displayLabel?)` — transactional. INSERTs the `entities` row; auto-merges if the (entity_type, canonical_value) pair already exists. Status becomes `approved` or `merged_into_existing`.
- `rejectEntityProposal(id, reason)` — transactional reject + change-log audit.

The scheduled `taxonomy-reevaluation` worker (`apps/workers/src/trigger/taxonomy-reevaluation.ts`) runs per-domain k-means clustering on stored claim embeddings, names each surviving cluster via a cheap synthesis call, skips clusters whose centroid already matches an existing `knowledge_sub_topics` row (cosine ≥ 0.88), and writes the remainder as `create_sub_topic` proposals into `taxonomy_proposals` for admin review. Domains with fewer than 30 approved, embedded claims are skipped at the activation gate; the worker never mutates the taxonomy directly.

### Architectural state — retrofit complete

```
OpenRouter is NOT in the inference path. sources/openrouter.ts provides enrichment-only (pricing + capability flags joined onto models fetched from direct provider APIs).
The Vercel AI SDK is forbidden inside packages/ai/src/providers/.
Every production AI call goes through OracleAIClient with the three
  direct provider adapters (Anthropic / Vertex / OpenAI raw SDKs).
Every model call has a context pack + usage detail row.
Every promotion is advisory-locked and race-safe.
Every claim insertion is hash-deduped.
Every taxonomy mutation is admin-gated.
Every synthesis output is validated; rejected versions preserved.
Every operationally-sensitive observability dashboard is read-only.
Every retrieval query carries an explicit RetrievalPlan.searchScope;
  global_fallback is logged with a structured warning and tagged in
  oracle_context_packs.selected_domains for audit.
Every worker resolves its model route through resolveModelRoute(),
  which handles both catalog routeIds and OpenRouter-style model IDs.
Wet-test passed end-to-end against the live Supabase project on
  2026-05-26 — first real claim rows landed with all observability
  metadata captured.
Both proactive interjection paths (lull-detection and live
  contradiction surfacing) post live chat messages gated by pure
  decision functions, with every decision logged to
  oracle_interventions for admin audit.
```

R11 (interjection engine) is complete. Both lull-interjection and live-contradiction paths post real chat messages; every decision is logged to `oracle_interventions` for admin audit.
