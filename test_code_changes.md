# test_code_changes.md — Vision transcription & claim-extraction test plan

**Audience:** a developer who just walked in and knows *nothing* about this app beyond the `.md` files. Read this top-to-bottom once before running anything.

**Last updated:** 2026-07-06. Delete or fold into `HANDOFF.md` once both tests below are complete and their results are recorded here.

**Why this doc exists:** We ingested a single swimlane process diagram ("Edge Home – Licensed Flow", internally filed as `Pop Creations Flow 12112025 (1).png`) and the Oracle drew a lot of **wrong conclusions** from it. We investigated the root causes, made some code changes, and now need to run **two tests** to prove things are better and to decide whether we can afford a stronger vision model. This doc contains all the background, the changes, prior results, and step-by-step instructions for both tests.

---

## 0. 60-second orientation: what this app does

The Oracle is an AI knowledge graph of how a home-decor company (POP Creations / Spruce Line) actually operates. Employees upload documents and images; the system extracts small, evidence-backed **claims** ("After X, team Y does Z") into a Postgres/Supabase database, where humans review them.

**The image pipeline (this is the whole story for these tests):**

```
image  ──►  [PASS 1: Vision model]  ──►  transcription TEXT  ──►  chunks  ──►  [PASS 2: Extraction model]  ──►  claims
           "transcribeImageToText"        (persisted as              (4k chars    "EXTRACTION_SYSTEM_PROMPT"     (rows in the
            document-ingestion.ts          document_chunks)           each)        + diagram addendum             `claims` table)
```

**The single most important fact:** the extraction model in Pass 2 **never sees the image.** It only sees the Pass-1 text. So if Pass 1 mis-reads the diagram, Pass 2 faithfully turns the mistake into confident claims. There is **no step anywhere that checks the claims against the actual image** — the provenance validator (R5) only checks that each claim quote is a verbatim substring of the *transcription*, not that the transcription is faithful to the *image*. Both tests below exist to close that blind spot.

**Key files (memorize these paths):**
| Path | What it is |
|---|---|
| `apps/workers/src/trigger/document-ingestion.ts` | The whole image pipeline. `IMAGE_TRANSCRIPTION_SYSTEM` (Pass-1 prompt, ~L315), `transcribeImageToText` (~L379), diagram extraction addendum (~L918), constants `VISION_TEMPERATURE`/`VISION_MAX_OUTPUT_TOKENS` (~L107), `documentIngestionTask` (~L1626). |
| `packages/ai/src/prompts/extraction-system.ts` | Pass-2 extraction prompt + Zod output schema. `EXTRACTION_PROMPT_VERSION` (bump on any prompt edit). |
| `packages/ai/src/routes/catalog.ts` | The model route catalog (every model + its provider + cache strategy). |
| `packages/ai/src/routes/defaults.ts` | Setting keys: `default_vision_route`, `default_vision_reasoning_effort`. |
| `packages/ai/src/client/standard-adapters.ts` | `buildStandardAdapters()` — the 6 provider adapters wired in (anthropic, vertex, google, openai, deepseek, qwen). |
| `packages/oracle-engines/src/extraction/cache-profitability.ts` | `decideCacheProfitability()` — when we create an explicit provider cache. |
| `packages/oracle-engines/src/extraction/candidate-hash.ts` | `computeCandidateHash()` — the dedup key (keys on summary text → near-dupes survive; see §3). |
| `apps/web/app/admin/ai/cache/page.tsx` | Admin UI that reads the `provider_cached_content` cache-tracking table. |

**The test document:** `document.id = 9d09fa89-3a46-465e-a98b-837287c9e22a`. This is the swimlane diagram both tests use.

---

## 1. Background: what went wrong (the conclusions we need to prevent)

We compared the 241 claims the system extracted from the diagram against a careful human reading of the same image. Seven classes of error came out. **These are your regression targets — Test 1 measures whether they're gone.**

1. **Cross-wiring (semantic).** The transcription said `RFQ to Factories → Factories provide "Details and Limitations"` and `Provide details in ClickUp → "Price"`. The image shows the opposite: an **RFQ produces a Price**; asking about limitations produces Details/Limitations. Endpoints were swapped.
2. **Wrong lane / owner.** "Agenda template / Kick off Meeting" is in the **Creative direction** lane in the image, but the transcription filed it under **Sales**, so ~10 claims blamed the wrong team.
3. **Self-contradiction.** "PPS Submit to licensor" is owned by the **Licensing Team**, but some claims said **Gina** does it (Gina only does the audit review just before). The claim set disagreed with itself.
4. **Flattened decision branch.** The diagram forks costing into **"New Product Type" → "Costing sheets/Tech Pack elaboration"** vs **"Existing Product" → "Costing sheets elaboration"**. Only one path survived; the branch labels ("New Product Type", "Existing Product", "For Customer Refresh") vanished.
5. **Dropped nodes.** Boxes present in the image but absent from all 241 claims: **SKUs creation** (Carlos), **Include in Task List** (Production), **Samples Order / TechPack request** (Production), **Production order** (Production), **Sampling** (Factories), **Licensor's revisions review** (Creative direction). Isolated boxes (few/no arrows) produce no claims because extraction is edge-driven.
6. **Massive duplication.** 56 distinct arrows → **241 claims (~4.3× per edge)**. The same arrow was emitted as a `dependency` **and** one or more `process_rule` claims, plus reworded restatements (e.g. proc#15 ≡ proc#16 verbatim; the "Price → Designs Approval" arrow alone spawned 5 claims).
7. **Policy over-labeling.** 46 arrows were re-cast from description into prescription ("team X **must** do Y") by the `claim_kind` classifier. A flowchart shows *sequence*, not *obligation*. (Note: the `claim_kind` classifier code is **not in this repo checkout** — `claim_kind` appears only in `oracle_master_spec.md` / `docs/oracle/07-knowledge-segmentation.md`; the writer that sets `claim_kind = 'policy' | 'observed_practice'` with `claim_kind_review_status = 'model_labeled'` lives elsewhere (another branch or a Supabase function). Finding it is a sub-task if we want to fix error #7 in code.)

### 1a. Ground truth for the diagram (use this to score Test 1)

The vision model reduced the image to a node list per swimlane plus **56 edges**. The corrected, human-verified structure is below. Treat this as the answer key. (If you want the raw 56-edge list the model produced, re-run Test 1 step A and diff.)

**Swimlanes (left→right):** Albert :) · Buyer · Sales · Creative direction · *Junior designer* · *Technical designers* · Creative designers · Sourcing · Production · Carlos · Gina · Licensing Team · *Licensor* · *Factories*. (Italic = external/support role. Carlos, Gina, Albert are named individuals with their own lanes.)

**Corrected owner/lane facts the transcription got wrong (score these explicitly):**
- `Agenda template / Kick off Meeting` → **Creative direction** (NOT Sales).
- `RFQ to Factories` → **Price** ; `Asking the factories about limitations` → **Details and Limitations** (endpoints, not swapped).
- `PPS Submit to licensor` → **Licensing Team** (NOT Gina).
- Costing fork is **two paths** gated by "New Product Type" vs "Existing Product".

**Boxes that must appear (were dropped):** SKUs creation, Include in Task List, Samples Order / TechPack request, Production order, Sampling, Licensor's revisions review.

**Conditional branches that must be preserved with their labels:** `If Sales confirms buyer approves the Price`, `If Audit: Pass` / `If Audit: Fail`, `For New Products` / `For existing products`, `With an Order` / `Before an Order`, licensor-comment split (`legal line/packaging` → Tech Pack Update vs `creative design` → Revisions implementation), and the costing fork (#4 above).

---

## 2. What we changed in the code (and what we deliberately did NOT change yet)

As of 2026-07-06 the working tree (`git status`) has these **uncommitted** changes. Run `git diff` to see them in full. Summary:

### 2a. Changes actually made (present in the working tree)
| File | Change | Purpose |
|---|---|---|
| `apps/workers/src/trigger/document-ingestion.ts` | Added `estimateDocumentInformationWeight()` and made `buildDocumentChunkWindows()` pack by *information weight* (headings/tables/diagram-edges/decision-terms weighted), not just char count. | Dense diagrams no longer overflow a window silently; more even extraction. |
| `apps/workers/src/trigger/claim-extraction.ts` | Added `EXTRACTION_MAX_OUTPUT_TOKENS = 32_000` on the message-extraction call. | Stop JSON truncation on dense output. |
| `packages/ai/src/client/oracle-ai-client.ts` | Swapped the inline 4-adapter map for `buildStandardAdapters()` (now includes **deepseek** and **qwen**); mock map adds deepseek/qwen too. | One source of truth for providers; **enables the 5-model comparison in Test 2**. |
| `packages/ai/src/providers/vertex-gemini-adapter.ts` | Replaced ad-hoc `prefixTokens >= 2048` cache gating with `decideCacheProfitability()` (25k tok & 3× reuse, or 100k & 2×). Threaded `expectedReuseCount`. | Cost-correct explicit caching; **directly relevant to Test 2's caching question**. |
| `apps/web/app/admin/ai/page.tsx`, `apps/web/app/admin/ai/cache/page.tsx` | Expanded admin cache/AI visibility (reads `provider_cached_content`: `status`, `cache_hit_ratio`, low-hit-ratio warnings). | Human-readable cache metrics for Test 2. |
| `packages/ai/package.json` + `packages/ai/src/__verify__/openai-qwen-cache-requests.ts` | New no-network regression gate `verify:openai-qwen-cache` that asserts the OpenAI/Qwen adapters emit the right cache request fields. | Proves cache request *shape* per provider without spending tokens. |

### 2b. Changes we analyzed and recommended but have NOT made yet
These are the fixes for the seven errors in §1. They are **not** in the tree; the tests below establish the baseline before we do them.
- **Vision (Pass 1):** route a stronger multimodal reasoning model + raise `default_vision_reasoning_effort`; set `VISION_TEMPERATURE` to 0 (route-aware); **de-prescribe** `IMAGE_TRANSCRIPTION_SYSTEM` so a capable model reasons about *any* visual instead of being forced into a rigid `[Shape]-->[B]` template; optional generic self-verify second pass. (Design principle from the owner: *do not encode diagram-type-specific rules; make the model self-sufficient across any visual input.*)
- **Extraction (Pass 2):** make the dynamic request diagram-aware — **one claim per relationship**, never the same edge under two claim types; kill the SOP-density instruction leaking onto the diagram path.
- **Dedup:** re-key `computeCandidateHash` on the relationship (evidence span + claimType) instead of summary wording.
- **`claim_kind`:** require explicit normative language ("must/always/required") before labeling `policy`; locate the out-of-repo classifier first.

---

## 3. Prior test results (so you don't repeat them)

From `HANDOFF.md` (2026-06-26 "extraction bake-off", same test doc `9d09fa89…`), with **vision held constant at `qwen/qwen3-vl-235b-a22b-thinking`** and each extraction model isolated into a one-element pool (so fail-over couldn't hide failures):

| Extraction model | Claims | Notes |
|---|---|---|
| `gpt-4o-mini` | 9 | thin |
| `gpt-4.1-mini` | 12 | thin |
| **`google/gemini-2.5-flash`** | **54** | **winner: best type variety, captured conditional branches, faithful verbatim edge quotes, 59.8s** |
| `vertex/gemini-2.5-flash` | 52 | all flat dependency claims |
| `gemini-3.1-flash-lite` | 5 | very thin |

**Current prod config (the baseline you are testing against):**
- `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking`
- `default_vision_reasoning_effort = medium`
- `default_extraction_route = google/gemini-2.5-flash`
- `model_pool_extraction = [google/gemini-2.5-flash, vertex_gemini_2_5_flash_extraction_primary, openai/gpt-4.1-mini]`
- `enforce_model_capabilities = true`, `default_extraction_reasoning_effort = off`

**Vision side-finding from HANDOFF (important):** `google/gemini-2.5-flash` vision is ~3× faster than qwen3-vl (33s vs ~90s) and gave the richest extraction, **but** it labeled some person-lanes by *department* — e.g. it dropped "Carlos" as an owner. qwen3-vl was kept specifically because it does **person-level lane attribution**. This is exactly the kind of quality difference Test 2 must quantify, not eyeball.

**The 241-claim re-run** analyzed in §1 came from a later rerun of the *whole* pipeline (`rerun-20260702T220901Z`), exported to a JSON snapshot with fields `document`, `chunks` (holds the transcription in `raw_text_preview`, truncated to 1000 chars each), and `claims` (each with `summary`, `claim_type`, `claim_kind`, `evidence[].exactQuote`). If such a snapshot exists for your run, it's the fastest way to diff; otherwise pull from the DB (§5).

---

## 4. TEST 1 — "What the system sees" vs "what a human sees" (faithfulness)

**Goal:** measure how faithfully Pass 1 transcribes the diagram and how faithfully Pass 2's claims reflect the image. Output is a scored faithfulness report, not a vibe check.

### Step A — Get the current transcription the system produced
The transcription is persisted as `document_chunks` for the document. Pull it:

```sql
-- All chunks that make up the vision transcription, in order.
select chunk_index, char_length(content) as len, content
from document_chunks
where document_id = '9d09fa89-3a46-465e-a98b-837287c9e22a'
order by chunk_index;
```
Concatenate `content` across chunks in `chunk_index` order → that is the full text the extraction model saw. (The JSON snapshot's `raw_text_preview` is truncated to 1000 chars; the DB `content` column is full — use the DB.)

### Step B — Get the claims the system produced
```sql
select c.id, c.claim_type, c.summary, c.impact_score, c.confidence_score,
       ce.exact_quote
from claims c
left join claim_evidence ce on ce.claim_id = c.id
where c.source_document_id = '9d09fa89-3a46-465e-a98b-837287c9e22a'   -- confirm the FK column name in schema.ts
order by c.created_at;
```
(If the column names differ, open `packages/db/src/schema.ts` and search for the `claims`, `claim_evidence`, `documents` tables. The snapshot in §3 shows the shape.)

### Step C — Score against the ground truth (§1a)
Fill this rubric. Every metric is a fraction with a numerator you can point to.

**Transcription faithfulness (Pass 1):**
- **Node recall** = (image boxes present in transcription) ÷ (total image boxes). The six boxes in §1a must be present.
- **Edge endpoint accuracy** = (edges whose *both* endpoints match the image) ÷ (edges). Catches cross-wiring (#1).
- **Edge direction accuracy** = fraction of edges pointing the correct way.
- **Lane/owner accuracy** = (nodes assigned to the correct swimlane) ÷ (nodes). Catches #2, #3.
- **Branch preservation** = (conditional branches with correct label + both paths) ÷ (branches in §1a). Catches #4.

**Claim faithfulness (Pass 2):**
- **Owner correctness** = (claims naming the correct team/person) ÷ (claims naming an owner).
- **Duplication ratio** = (claims) ÷ (distinct relationships). Target ≈ 1.0; baseline was 4.3.
- **Cross-type duplication** = count of relationships emitted under >1 `claim_type` (target 0).
- **Policy over-labeling** = (claims labeled `policy` without normative words in the quote) ÷ (policy claims).

### Step D — Report
Produce `test1_results.md` (or append here) with the rubric filled, plus a short list of every §1 error that is still present. **Definition of pass:** all six dropped boxes present, endpoint accuracy = 100% on the RFQ/Price and Agenda-template cases, no self-contradiction on PPS Submit, both costing paths present, duplication ratio ≤ 1.3.

### How to (re)run the pipeline to test a code change
1. Make sure the doc is re-ingestable. The single-document worker is `documentIngestionTask` (`id: 'document-ingestion'`, payload `{ documentId: "<uuid>" }`).
2. Two ways to trigger it:
   - **Trigger.dev MCP / dashboard:** trigger task `document-ingestion` with payload `{"documentId":"9d09fa89-3a46-465e-a98b-837287c9e22a"}` (project `proj_wgpzsvhmsopqhvwqaycn`). See `CLAUDE.md` → Trigger.dev MCP.
   - **Admin UI:** the app re-dispatches ingestion from the documents admin route (`apps/web/app/api/admin/documents/route.ts`). Re-uploading or re-processing the doc enqueues the same task.
3. **Re-ingest is destructive to the prior claims for that doc if the worker upserts** — snapshot the current `claims`/`document_chunks` first (Steps A/B) so you can diff old vs new.

---

## 5. TEST 2 — Five vision models head-to-head + prompt-cache quality

**Goal (two parts):**
1. **Quality:** which of 5 vision models transcribes the diagram most faithfully (score with the *same* Test 1 rubric).
2. **Caching:** how well each model does **context/prompt caching**, because — in the owner's words — *"very good caching would mean we could use a better/more expensive model."* If an expensive model caches the large stable prefix cheaply, its effective per-run cost drops enough to justify it.

### 5a. The 5-model slate (adjust as needed; all are vision-capable and wired via `buildStandardAdapters`)
| # | routeId / model | Provider | Cache strategy (`catalog.ts`) | Why include |
|---|---|---|---|---|
| 1 | `qwen/qwen3-vl-235b-a22b-thinking` | qwen | `qwen_explicit_context_cache` | **Current baseline** (person-level lanes) |
| 2 | `google/gemini-2.5-flash` | google | `none` (google) / vertex has caching | Fast, rich, but department-labels lanes |
| 3 | `anthropic/claude-sonnet-4-6` | anthropic | `anthropic_explicit_breakpoints` | Frontier reasoning — the "can we afford better?" candidate |
| 4 | `openai/gpt-4o` | openai | `openai_automatic_with_cache_key` | Automatic caching, strong vision |
| 5 | `vertex/gemini-2.5-flash` | vertex | `vertex_implicit_or_explicit_by_context_size` | Same model as #2 but the **explicit-cache** code path (`decideCacheProfitability`) |

Confirm each route exists/`enabled` in `catalog.ts`; add a vision route if you want a model that isn't catalogued yet (e.g. a newer Gemini/Claude). deepseek has an adapter but **no vision route** — don't put it on the vision slate.

### 5b. Two ways to run the comparison — pick one

**Option A (low-code, uses the real pipeline): flip the setting + re-ingest, per model.**
For each model on the slate:
1. `POST /api/admin/settings` with `{ "key": "default_vision_route", "value": "<model route>" }` (route: `GET/POST /api/admin/settings`, upsert single setting by key). Optionally also set `default_vision_reasoning_effort`.
2. Snapshot then re-ingest the doc (§4 "How to re-run").
3. Pull the new transcription (§4 Step A) and the per-call usage from `model_runs` / usage-details (see 5c).
4. Score transcription with the Test 1 rubric.
5. Restore `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking` when done.

**Option B (repeatable harness script): write a `__verify__`-style runner.**
Model it on `packages/ai/src/__verify__/openai-qwen-cache-requests.ts` and `vertex-inline-image.ts`. The script:
1. Loads the test image bytes, builds the vision message (`buildVisionMessageContent(mimeType, base64, requestText)` — exported/near-exported in `document-ingestion.ts`; copy the shape).
2. For each of the 5 routes, calls `client.runText(...)` exactly as `transcribeImageToText` does (same `IMAGE_TRANSCRIPTION_SYSTEM`, `highResolutionVision: true`).
3. Records: transcription text, `result.usage` (`inputTokens`, `cachedInputTokens`, `cacheWriteTokens`, `outputTokens`, `reasoningTokens`), latency, provider, modelId.
4. **To test caching, call each model 3× with the same stable prefix** (see 5d) and record cached-token growth on calls 2–3.
Run with `pnpm --filter @oracle/ai exec tsx src/__verify__/<your-file>.ts`. This is the cleaner path for the caching half because you control the reuse count.

### 5c. Where the cache/usage numbers live
- **Per call:** `model_runs` (and its usage-details rows) carry `input_tokens`, `cached_input_tokens`, `cache_write_tokens`, `output_tokens`, `reasoning_tokens`, `raw_usage_json`, `provider_request_id`. Query by the `model_run` inserted during ingestion (task_type `document-ingestion-vision`).
- **Explicit-cache lifecycle:** `provider_cached_content` (R7 tracking table) — `status`, `cache_hit_ratio`, source token estimate, reuse count. Surfaced in the **admin cache page** at `/admin/ai/cache` (reads this table; flags entries with `cache_hit_ratio < 0.15`).
- **Decision logic:** `decideCacheProfitability()` only creates an *explicit* cache at **≥25k tokens & ≥3 reuses**, or **≥100k & ≥2**. The diagram transcription is ~2.5k tokens, so **explicit caching will NOT trigger for a single small image** — you'll be measuring **implicit** caching (provider-managed, free) via `cached_input_tokens > 0` on repeat calls. Say so in the report; don't mistake "no explicit cache row" for "caching failed."

### 5d. How to make the caching test meaningful (read this carefully)
Caching only pays off when a **stable prefix is reused**. In this pipeline the reusable prefix is the **system prompt + document corpus**, reused across extraction windows and across re-runs. A single tiny diagram won't exercise it. To get signal:
- **Reuse loop:** call each model ≥3× with an *identical* system prompt + input, back-to-back within the provider's cache TTL (Vertex explicit TTL is set to 15 min in code; Anthropic/OpenAI automatic caches have their own short TTLs). Measure `cached_input_tokens` on calls 2 and 3 vs call 1.
- **Big-prefix variant (optional but recommended):** to reach the 25k-token explicit-cache threshold and really stress caching, prepend a large stable context block (or test on a *large* multi-page document instead of the tiny diagram) and set `expectedReuseCount ≥ 3` in the provider hints. This is the scenario that decides "can we afford a frontier model" — because that's where caching discounts dominate the bill.

### 5e. Cost model (how to turn cache numbers into a decision)
For each model compute **effective $/run**:
```
cost = uncached_input_tokens * price_in
     + cached_input_tokens   * price_in_cached      (cached is much cheaper per provider)
     + cache_write_tokens    * price_in_cache_write (one-time, if explicit)
     + output_tokens         * price_out
```
Pull per-provider prices from each provider's pricing page (record the date + source in the report). Then produce a single table:

| Model | Faithfulness score (Test-1 rubric) | Latency | Cached-token % on reuse | Effective $/run (1 call) | Effective $/run (steady-state w/ cache) | Verdict |
|---|---|---|---|---|---|---|

**The decision rule the owner cares about:** if a more faithful, more expensive model shows a high cached-token % on reuse (so its *steady-state* $/run is competitive), we can switch to it. A model that's cheap but caches poorly may lose on steady-state cost at volume.

### 5f. Guardrails
- Run the no-network shape gate first so you don't waste spend on a broken request: `pnpm --filter @oracle/ai exec tsx src/__verify__/openai-qwen-cache-requests.ts` (and `verify:vertex-inline-image` for the Vertex image path).
- Isolate each model (Option A already does, since vision routes directly off `default_vision_route` — there is **no** `model_pool_vision`). For Option B, call one route at a time.
- Restore prod settings when finished (`default_vision_route = qwen/qwen3-vl-235b-a22b-thinking`, `default_vision_reasoning_effort = medium`).

---

## 6. Environment & tooling the new dev needs

- **Secrets / env:** local `.env.local` currently points at the **old** Supabase (`oracle.old`, `vokucjpanhvqunimlvsp`) per `HANDOFF.md`. Runtime keys, OpenRouter, Trigger.dev secret, and Vercel OIDC are stored in **1Password vault `vibe_coding`** as Secure Notes (see the exact note titles in `HANDOFF.md`). **Do not run prod migrations from local env** without overriding `DIRECT_URL` to the current-prod 1Password session pooler. Current prod Supabase project ref: `eqccjfbyrywsqkxxpjvg`.
- **Database reads:** use the Supabase MCP for reads (`CLAUDE.md` → Supabase MCP), or `psql` with the prod session pooler from 1Password. Never commit connection strings.
- **Running workers / triggering tasks:** Trigger.dev MCP (project `proj_wgpzsvhmsopqhvwqaycn`) can inspect/trigger/deploy. `apps/web/lib/trigger.ts` lists task wiring.
- **Admin UI:** `/admin/ai` (models/settings), `/admin/ai/cache` (cache metrics). Settings API: `GET/POST /api/admin/settings`.
- **Provider adapters:** `packages/ai/src/providers/*` (anthropic, vertex-gemini, google-gemini, openai, deepseek, qwen). Cache request-shape gates in `packages/ai/src/__verify__/`.
- **Prompt versioning rule:** any edit to `EXTRACTION_SYSTEM_PROMPT` (or the vision prompt) MUST bump `EXTRACTION_PROMPT_VERSION` in `extraction-system.ts` and be logged in `DECISIONS.md` (repo rule, stated in the prompt file header).
- **Do not** bulk-read `docs/oracle/`, generated Drizzle SQL, or `pnpm-lock.yaml` (`.claudeignore` / `AGENTS.md`).

---

## 7. Deliverables checklist

- [ ] **Test 1 report:** faithfulness rubric filled for the *current* pipeline; list of which §1 errors remain. Snapshot of transcription + claims used.
- [ ] **Test 2 report:** 5-model table (faithfulness × latency × cached-token % × effective $/run steady-state) + a one-line recommendation on whether to move off qwen3-vl and to which model.
- [ ] **Raw data saved** (transcriptions, `model_runs` usage rows, cache-table snapshots) next to the reports so results are reproducible.
- [ ] **Prod settings restored** to the §3 baseline after Test 2.
- [ ] Results appended to this file (or linked) and the `HANDOFF.md` pointer updated.

---

## 8. Fast path (if you only have an hour)

1. Pull current transcription + claims for `9d09fa89…` (§4 A/B). 2. Score against §1a ground truth (§4C). 3. Run Test 2 Option A for just **2** models — baseline `qwen3-vl` vs `anthropic/claude-sonnet-4-6` — and compare faithfulness + `cached_input_tokens` on a 3× reuse loop. That alone tells you whether a stronger model is worth a full bake-off.
