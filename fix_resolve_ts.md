# Fix Plan: Runtime model-capability enforcement (stop trusting unknown models)

Status: **NOT STARTED.** This document is a complete, self-contained brief so a developer with zero prior context can implement it. Written 2026-06-25.

---

## 0. What this project is (orientation for a fresh developer)

The Oracle is an evidence-backed enterprise knowledge graph (POP Creations / Spruce Line). Employees chat with it and upload documents; background workers extract "claims" with quote-level evidence; deterministic validators gate promotion into approved knowledge. **Read `AGENTS.md` first** — it is the canonical operating guide. Key facts you need for THIS task:

- Monorepo: `pnpm` + `turbo`. Packages: `apps/web` (Next.js), `apps/workers` (Trigger.dev background tasks), `packages/ai` (the AI client, provider adapters, model catalog + routing), `packages/db` (Drizzle schema), `packages/oracle-engines` (deterministic extraction/promotion).
- **All inference goes through `OracleAIClient`** (`packages/ai/src/client/`) → `ModelRouter` (`packages/ai/src/routing/model-router.ts`) → a provider adapter (`packages/ai/src/providers/*-adapter.ts`). Routes/workers must NOT call provider SDKs directly.
- There are **3 frozen pipeline roles**: `interview` (employee chat), `extraction` (claims from messages/documents), `synthesis` (Brain narrative). Plus **auxiliary models** (`packages/ai/src/routes/auxiliary.ts`): currently `vision` (image transcription) and `general`, and a `translation` route. Each role/aux model has an admin-selected model stored in a `settings` row (e.g. `default_extraction_route`, `default_vision_route`).
- The model catalog lives in the Postgres table **`model_capabilities`** (one row per discovered model, with capability flags + pricing). It is populated by `refreshModelCatalog` (`packages/ai/src/model-capabilities/`) from the 5 provider list APIs + OpenRouter enrichment.

## 1. The problem (what to fix and why it matters)

The admin UI lets you pick a model per role/aux slot. The **UI filters** the candidate list by capability (e.g. the vision picker only shows vision-capable catalog models; see `apps/web/lib/stage-requirements.ts`). **But the runtime does NOT re-check.** When a route is resolved at runtime, `packages/ai/src/routes/resolve.ts` → `makeSyntheticRoute()` fabricates a route for ANY `provider/model` string with `SYNTHETIC_CAPS` where **every capability flag is hard-coded `true`**:

```ts
const SYNTHETIC_CAPS = {
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  costTier: 'balanced_default',
  enabled: true,
};
```

So an admin-saved-but-stale model id, a manually-inserted `settings` value, or any `provider/model` string that isn't in the curated catalog is **assumed to support vision / structured output / tools** even if it doesn't. The "right tool for the job" invariant is enforced only in the UI, not at dispatch.

**Why this is not hypothetical — the incident that motivated this:** earlier in 2026-06 the `default_vision_route` was set to `google/gemini-3.1-flash-image-preview`, which is an **image-GENERATION** model, not an image-*reading* (vision) model. Nothing rejected it. It produced inconsistent/hallucinated transcriptions of an uploaded flowchart, and the failure was masked for hours by an unrelated silent fallback. Runtime capability enforcement would have refused that model up front.

### What was already done this session (do NOT redo)
- `makeSyntheticRoute()` now emits a `console.warn` that capabilities are "ASSUMED true and NOT verified". That is **visibility only** — it does not enforce anything. This task replaces that with real enforcement. (See the warn in `packages/ai/src/routes/resolve.ts`, added 2026-06-25.)

## 2. Where the code lives (exact map)

| Thing | File / symbol |
|---|---|
| Synthetic route fabrication (the bug) | `packages/ai/src/routes/resolve.ts` → `makeSyntheticRoute()`, `SYNTHETIC_CAPS`, `resolveModelRoute()` |
| Route resolution from settings (DB-aware) | `packages/ai/src/routes/from-settings.ts` → `resolveRouteFromSettings(db, role)`, `resolveAuxiliaryRouteFromSettings(db, auxId)` |
| Curated catalog (known-good routes w/ real caps) | `packages/ai/src/routes/catalog.ts`, defaults in `packages/ai/src/routes/defaults.ts` |
| Capability source of truth (DB) | `model_capabilities` table (`packages/db/src/schema.ts`); read API `apps/web/app/api/admin/model-catalog/route.ts` (`passesQualityFilter`) and `apps/web/app/api/admin/models/route.ts` |
| Stage requirement predicates (what each role needs) | `apps/web/lib/stage-requirements.ts` (shared by the UI picker) |
| Auxiliary model registry (vision/general) + required capability | `packages/ai/src/routes/auxiliary.ts` (`AUXILIARY_MODELS`, each entry can have `requiredCapability`) |
| Where vision is invoked | `apps/workers/src/trigger/document-ingestion.ts` → `transcribeImageToText()` (resolves via `resolveAuxiliaryRouteFromSettings(db,'vision')`) |
| The OracleModelRoute type (capability fields) | `packages/ai/src/routes/types.ts` |

**Critical constraint:** `resolve.ts` is currently **pure and synchronous** (no DB access). The capability truth lives in the `model_capabilities` Postgres table, which requires a DB handle. So enforcement cannot happen entirely inside `resolve.ts` as written — see the design.

## 3. The fix — design

**Goal:** when a model is selected for a capability-sensitive role/slot, verify against `model_capabilities` that it actually has the required capability. If it does not (or the model is unknown and the capability is required), **refuse loudly** (throw a typed error) instead of fabricating `supportsVision: true` and silently dispatching.

Two layers:

### Layer A — Resolution-time enforcement (DB-aware path)
Add capability verification to the DB-aware resolvers in `from-settings.ts` (these already have `db`):

1. Define, per role/aux slot, the **required capabilities** (reuse/centralize the predicates from `apps/web/lib/stage-requirements.ts` — move the source of truth into `packages/ai` so both UI and runtime share it; e.g. a new `packages/ai/src/routes/capability-requirements.ts`). Example: `extraction` → `supportsStructuredOutput`; `vision` aux → `supportsVision`; `interview` → `supportsVision` + `supportsToolCalling` + `supportsStructuredOutput`; `synthesis` → `supportsStructuredOutput` + `supportsReasoningControls`.
2. When resolving, look up the chosen model in `model_capabilities`:
   - **Found** → use its REAL capability flags to build the route (replace `SYNTHETIC_CAPS` with the looked-up values for the dynamic path). If a required capability is missing → throw `ModelCapabilityError(role, modelId, missingCapability)`.
   - **Not found in catalog** → the model is genuinely unknown. Policy (make it a setting, default **fail-closed for capability-sensitive roles**): refuse with `ModelCapabilityError` for roles that require a non-trivial capability (vision, structured output, tools); allow for capability-agnostic uses with a loud warn. Rationale: an uncatalogued model in the vision slot is exactly the incident.
3. Keep curated-catalog routes (`catalog.ts`) untouched — they already carry verified capabilities.

### Layer B — A typed, catchable failure (no silent fallback into a worse model)
- Add `class ModelCapabilityError extends Error` in `packages/ai/src/routes/` carrying `{ role, modelId, missing }`.
- Decide fallback behavior deliberately. The `ModelRouter` has `fallbackOnError: true`. A capability error should **NOT** silently fall back to a different model for capability-sensitive work (that reintroduces the masking). Options:
  - Preferred: capability errors are thrown at resolution time (before dispatch), so the caller (e.g. `transcribeImageToText`, the chat route) surfaces a clear "selected model X cannot do Y — pick a capable model in Admin → Settings" error. The doc/job is marked `failed` with that message (this session already made `document-ingestion` mark `failed` on extraction error).
  - Do NOT add capability errors to `ModelRouter`'s fallback conditions (`packages/ai/src/routing/model-router.ts` `fallbackReason`/conditions).

### Layer C — Keep the catalog honest (defense in depth)
- The vision incident model (`*-image-preview`) should ideally never have `supportsVision: true` in the catalog. Check how `refreshModelCatalog` sets `supportsVision` for `*-image-*` / generation-preview models (`packages/ai/src/model-capabilities/sources/*.ts` + the post-enrichment filters). If image-generation models are being flagged vision-capable, fix the enrichment so the picker never offers them either. This is the upstream complement to runtime enforcement.

## 4. Step-by-step implementation

1. **Centralize capability requirements.** Create `packages/ai/src/routes/capability-requirements.ts` exporting `requiredCapabilitiesFor(roleOrAuxId): Array<keyof OracleModelRoute['caps']>`. Port the predicates from `apps/web/lib/stage-requirements.ts`; then have `stage-requirements.ts` import from the new shared module so the UI and runtime can never drift.
2. **Add `ModelCapabilityError`** in `packages/ai/src/routes/errors.ts` (or alongside `resolve.ts`). Export from `packages/ai/src/routes/index.ts`.
3. **Add a capability lookup** helper that, given a `db` + model id (or `provider/modelId`), returns the `model_capabilities` row (or null). Put it where DB-aware route code lives (`from-settings.ts` already imports `db`). Normalize ids the same way the catalog join does (dash→dot, date-stripping) — see `packages/ai/src/model-capabilities/sources/openrouter.ts` for the existing normalization.
4. **Enforce in `resolveRouteFromSettings` and `resolveAuxiliaryRouteFromSettings`** (`from-settings.ts`): after determining the chosen `modelIdOrRouteId`, if it resolves to a synthetic/dynamic route (not a curated catalog route), look up real caps and validate against `requiredCapabilitiesFor(role)`. Throw `ModelCapabilityError` on a missing required capability or on unknown-model-for-sensitive-role. Pass the real caps into `makeSyntheticRoute` so the synthetic route reflects reality (add an optional `caps` arg to `makeSyntheticRoute`; default to `SYNTHETIC_CAPS` only when truly unknown AND allowed).
5. **Add a settings flag** `enforce_model_capabilities` (default `true`) so the behavior can be disabled in an emergency without a redeploy (read it in the resolver). Document it in `docs/configuration.md`.
6. **Surface the error at the call sites** so it's actionable:
   - `apps/workers/src/trigger/document-ingestion.ts` `transcribeImageToText` — let it propagate; the worker already marks the document `failed` with the error.
   - `apps/web/app/api/chat/route.ts` — return a 400/422 with a clear message naming the model + missing capability.
7. **Fix the catalog enrichment** (Layer C) if image-generation models are flagged `supportsVision`.
8. **Update docs:** `AGENTS.md` §10 (add a quirk: "runtime enforces model capabilities; a wrong-tool model is refused, not silently fabricated"), `docs/configuration.md` (the new flag), `DECISIONS.md` (record the fail-closed-for-unknown decision).

## 5. Edge cases / gotchas

- **`resolve.ts` is sync/no-DB.** Don't try to make it async/DB-aware in place (it's imported widely). Do the enforcement in the DB-aware `from-settings.ts` layer, or thread the looked-up caps in.
- **Curated catalog routes** (`catalog.ts`) must keep working unchanged — they carry verified caps and are the happy path. Only the *synthetic/dynamic* path needs enforcement.
- **OpenRouter enrichment gaps:** a legit model can be missing pricing/flags if OpenRouter was down when the catalog refreshed. Don't hard-fail a known-good model just because enrichment is incomplete — prefer "capability present OR unknown-but-curated" logic, and lean on the curated catalog for the 3 pipeline roles.
- **Boot resilience principle (do not violate):** the system must still boot if a provider key is missing (`buildStandardAdapters` skips absent providers — and now logs loudly, fixed 2026-06-25). Capability enforcement is about *model selection*, not provider availability; keep them separate.
- **`general` aux model** has no hard capability requirement — don't over-enforce it.
- The dynamic-route smoke (`packages/ai/src/__verify__/oracle-ai-client-smoke.ts`, run via `pnpm --filter @oracle/ai verify:r2`) currently asserts `qwen/qwen3.7-plus` resolves dynamically. Make sure your enforcement doesn't break that legitimate dynamic route (qwen3.7-plus is a real model; it should pass for extraction which needs structured output).

## 6. Testing / acceptance

- Add a smoke gate (extend `verify:r2` or a new `verify:capability-enforcement`) asserting:
  1. A vision-incapable model selected for the `vision` aux slot → `ModelCapabilityError`.
  2. A vision-capable catalog model → resolves fine.
  3. An unknown model for `extraction` with `enforce_model_capabilities=false` → resolves (flag off).
  4. The legit dynamic route (`qwen/qwen3.7-plus`, extraction) still resolves.
- `corepack pnpm --filter @oracle/ai typecheck` and the full `verify:*` suite green.
- Manual: set `default_vision_route` to a non-vision model in Admin → Settings, upload an image, confirm the document is marked `failed` with a clear "model X lacks vision" message (NOT a silent Gemini fallback).

**Acceptance criteria:** a capability-sensitive role/aux slot cannot dispatch to a model that lacks the required capability; the failure is a clear, surfaced error naming the model + missing capability; curated routes and legit dynamic routes are unaffected; behavior is toggle-able via `enforce_model_capabilities`.

## 7. How to run / deploy (logistics for a fresh dev)

- Worker changes deploy to Trigger.dev: `corepack pnpm --filter @oracle/workers run deploy` (or the Trigger MCP `deploy`). Web changes deploy via Vercel on push to `main`.
- DB reads during dev: `.env.local` may point at the OLD Supabase project; production is `eqccjfbyrywsqkxxpjvg`. The prod **session pooler** connection string is in 1Password (`Supabase DB Direct URL - The Oracle (CURRENT PROD …)` → field `oracle_session_pooler`); the direct host is IPv6-only and won't resolve from a v4 box. See `AGENTS.md` §10.
- Trigger schedule slots are at 10/10 — do not add a new `schedules.task()`.
