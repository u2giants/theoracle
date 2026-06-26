# Test Plan: validate the model-routing refactor + the whole image→claims pipeline

Status: **READY TO EXECUTE.** Self-contained — written for someone with ZERO prior knowledge of this project or what changed. Written 2026-06-25 (evening).

If you read nothing else: the riskiest change here (the "no-fallback / pool-as-chain" routing refactor) sits **underneath every AI call in the system**. Test all four inference roles end-to-end (Section 6) before trusting anything else. A green typecheck does NOT prove inference still works.

---

## 1. What this system is (5-minute orientation)

**The Oracle** is an evidence-backed enterprise knowledge graph for a company (POP Creations / Spruce Line). Employees chat with it and upload documents; background jobs read messages/documents and extract **claims** (operational facts) with a verbatim **quote** as evidence; deterministic validators decide which claims get promoted into approved knowledge; a "Brain" synthesizes narratives from approved claims.

It is a `pnpm` + `turbo` TypeScript monorepo:

- `apps/web/` — Next.js web app + admin UI + API routes. Deployed to **Vercel** (auto-deploys on push to `main`).
- `apps/workers/` — background jobs ("tasks") on **Trigger.dev**. Deployed manually.
- `packages/ai/` — the AI client, the model **router**, provider **adapters**, the model catalog. **Every LLM call goes through here.**
- `packages/db/` — Drizzle schema + migrations (Postgres on **Supabase**).
- `packages/oracle-engines/` — deterministic extraction/validation/promotion logic.

**How an AI call flows (memorize this — the refactor changed it):**

```
caller (worker or chat route)
  -> OracleAIClient.runText() / runObject()      (packages/ai/src/client/oracle-ai-client.ts)
    -> resolve which model(s) to try             (packages/ai/src/routes/...)
      -> ModelRouter dispatches                   (packages/ai/src/routing/model-router.ts)
        -> a provider adapter makes the real call (packages/ai/src/providers/*-adapter.ts)
```

There are **3 pipeline roles**: `interview` (employee chat), `extraction` (claims from text), `synthesis` (Brain). Plus **auxiliary models**: `vision` (transcribe an uploaded image to text), `translation`, `general`.

The admin picks a model per role/aux at **Admin → Settings** (`/admin/settings`). Each pipeline stage also has an **approved pool** — a settings row like `model_pool_extraction = ["google/gemini-3.1-flash-lite","qwen/qwen3.7-plus","qwen/qwen3.7-max"]`.

Key terms you'll see:
- **route / routeId** — an identifier for "use this provider+model with these settings."
- **provider adapter** — the code that talks to a specific vendor (Anthropic, OpenAI, Vertex/Google Gemini, DeepSeek, Qwen/DashScope).
- **fallback** — what happens when the chosen model can't run. **This is the thing that was just rewritten.**
- **claim / candidate** — an extracted fact; a candidate is a not-yet-validated claim.
- **document_chunks** — the text an image/document was turned into; claims must quote a chunk verbatim.

---

## 2. Why this test plan exists — the background (what went wrong, and what changed)

This session chased a bug — "uploaded flowchart produced ~100 useless claims" — that unravelled into a chain of deeper problems. Understanding them tells you WHAT to test and WHY.

### The original symptom
A user uploaded a swimlane flowchart image. The pipeline produced ~100 shallow, often wrong claims. Investigation found the image is processed in **two passes**: Pass 1 a *vision* model transcribes the image to text; Pass 2 an *extraction* model reads that text and emits claims. Both passes had problems.

### The thing that wasted hours: SILENT FALLBACK to a hidden hard-coded model
The admin had selected Qwen models for vision and extraction. But the Qwen **provider key wasn't set in production**, so the Qwen adapter wasn't even constructed. When a Qwen route tried to run, the old `ModelRouter` **silently switched** to a **hard-coded** fallback model (`vertex_gemini_2_5_flash_extraction_primary`, i.e. Gemini 2.5 Flash) — a model that **wasn't even in the approved pool** — and **reported success**. So:
- The admin's selected model was NOT what ran.
- Nobody was alerted.
- Every debugging step was looking at the wrong model's output.

This same hidden fallback existed in two layers: the router's per-route `fallbackRouteId`, and per-worker `FALLBACK_ROUTE_ID` constants for the "setting unset" case. **All of this hard-coded fallback was removed in the refactor under test.**

### What the refactor (now in code) changed
The owner directive: **no silent fallback, ever; every failure fails loudly; the approved POOL becomes the fallback chain.** Concretely:
- `fallbackRouteId`, `DEFAULT_ORACLE_ROUTES`, and all worker `FALLBACK_ROUTE_ID` constants are **deleted**.
- New code (`packages/ai/src/routes/candidates.ts`, `errors.ts`, `capability-requirements.ts`, `attempt-logging.ts`) builds an **ordered candidate list** from the approved pool (primary = the selected model, then the rest of the pool), tries them **in order**, records **every attempt**, and:
  - if a model fails → advance to the **next approved + capability-valid** model, loudly;
  - if **all** fail → throw `AllCandidatesFailedError` (the job is marked `failed`);
  - if **no** model is configured → throw `NoConfiguredModelError` (no hidden default runs).
- **Capability enforcement** (`fix_resolve_ts.md`): a model is only used for a slot if it actually has the required capability (e.g. a non-vision model can't be used for the vision slot). This prevents the *other* root cause — an image-**generation** model had been wrongly selected as the vision model.
- A new migration `78_fail_loud_model_routing_settings.sql` and (likely) a `model_run_attempts` record of each attempt.

### The other problems found (all relevant to testing)
- **Vision model was wrong** (an image-*generation* preview model used for image *reading*) → fixed by selecting `qwen/qwen3-vl-235b-a22b-thinking` and by capability enforcement.
- **Image was sent to the model in the wrong shape** on a provider fallback → fixed by making the image payload **provider-neutral** and translating it inside each adapter at dispatch.
- **Extraction output truncated** (no output-token budget) → fixed by adding `maxOutputTokens` to the Gemini/Vertex `generateObject` calls.
- **Extraction model conformance:** `qwen/qwen3.7-plus` produces **loose** (tool-call) structured output and malforms fields, so the strict schema rejects the whole batch → **0 claims**. **Not yet fixed by switching models** — the recommended fix is to select `google/gemini-3.1-flash-lite` (native strict JSON). See Section 7.
- **A pile of silent-failure "swallows"** were made loud (see Section 9 of the issue inventory).
- **`fix_claim_extr.md` (conversation-aware message batching) was NOT implemented** — still a known weakness.

A complete issue inventory is in **Appendix A**.

---

## 3. Before you test: prerequisites & access

You CANNOT meaningfully test until all of these are true. Verify each.

1. **Migration applied to prod.** `78_fail_loud_model_routing_settings.sql` must be applied. Run `corepack pnpm db:migrate` (ships journaled Drizzle migrations + hand-written SQL). If unsure, run `corepack pnpm db:check-drift`.
2. **Worker redeployed.** `corepack pnpm --filter @oracle/workers run deploy` (the `run` keyword is required). Note the new worker version. (Reason: prod worker `v20260625.11` predates this refactor and also still carries some reverted experiments.)
3. **Web deployed.** Vercel auto-deploys on push to `main`; confirm the latest `main` deployment is live.
4. **Provider keys present in prod** (Trigger.dev prod env + Vercel): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, and for Qwen: `DASHSCOPE_API_KEY` **plus** `DASHSCOPE_BASE_URL = https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (the Qwen models are intl-only).
5. **Prod DB read access (for verification queries).** Use the **session pooler** connection string from 1Password item *"Supabase DB Direct URL - The Oracle (CURRENT PROD …)"* → field **`oracle_session_pooler`**. The *direct* host is IPv6-only and won't resolve from a v4 machine. Example query runner (run from inside the repo so `postgres` resolves):
   ```bash
   # in C:\repos\oracle
   PROD_URL="<oracle_session_pooler value>" node packages/db/some_query.mjs
   ```
   (or use the Supabase dashboard SQL editor / Supabase MCP for read-only queries.)
6. **Trigger.dev access** to trigger tasks and read runs (the Trigger MCP is connected for project `proj_wgpzsvhmsopqhvwqaycn`, prod env), or the Trigger dashboard.
7. **An admin login** to the web app for the Admin → Settings / Documents / AI pages.

**Static gates (run first; cheap):**
```bash
corepack pnpm -r typecheck
corepack pnpm --filter @oracle/ai run verify:r2          # rewritten for the new routing behavior
corepack pnpm --filter @oracle/ai run verify:vertex-inline-image
corepack pnpm --filter @oracle/engines run verify:r5
corepack pnpm --filter @oracle/engines run verify:r7
corepack pnpm lint
corepack pnpm build
```
All must pass. A failure here blocks everything below. **But passing here does NOT prove runtime inference works** — that's Sections 4–8.

---

## 4. Test priority order (do them in this order)

1. **Section 6 — Routing refactor regression** (highest risk; under everything).
2. **Section 5 — Verbose-fail / capability behavior** (the point of the refactor).
3. **Section 7 — Image → claims end-to-end** (the original goal).
4. **Section 8 — Silent-failure fixes fire** (the anti-masking work).
5. **Section 8.x — Chat attachments, dead-end picker, Qwen region.**

---

## 5. Verbose-fail & capability behavior (the core of the refactor)

Goal: prove there is **no silent fallback** and failures are loud, pool-bounded, and recorded.

| # | Test | How | Expected (PASS) | Failure signature |
|---|---|---|---|---|
| 5.1 | Primary model fails → auto-advance to next APPROVED pool model | Temporarily set a stage's primary (`default_extraction_route`) to a model whose provider key is intentionally missing, keep a working model later in `model_pool_extraction`. Run an extraction. | The job succeeds using the **next approved pool model**; `model_run_attempts` (or attempt log) shows the first model **failed** and the second **ran**; logs are loud. | It silently "works" on a model NOT in the pool, or no attempt record exists. |
| 5.2 | All candidates fail → loud aggregate error | Make every model in a stage's pool unusable (e.g. all keys missing). Run that stage. | `AllCandidatesFailedError` naming every model + reason; the job/document is marked `failed` with that message. | A hidden hard-coded model runs, or the job reports success/`complete`. |
| 5.3 | No model configured → loud error | Clear `default_<stage>_route` (and pool) for a stage. Run it. | `NoConfiguredModelError("No model configured for <stage> …")`. | A hard-coded default runs. |
| 5.4 | Capability enforcement | Select a **non-vision** model for the vision slot (`default_vision_route`). Upload an image. | The non-vision model is **refused/skipped** (capability error), not silently used; the failure is visible. | The non-vision model runs and produces garbage, OR an image-generation model is accepted as "vision." |
| 5.5 | No `fallbackRouteId` anywhere | `rg "fallbackRouteId|DEFAULT_ORACLE_ROUTES|FALLBACK_ROUTE_ID" packages apps` | **No matches** (except possibly in tests/this doc). | Any live reference remains. |
| 5.6 | Attempts are durably recorded | After 5.1/5.2, query the new attempts table (`model_run_attempts` or equivalent — see `packages/ai/src/routes/attempt-logging.ts`). | One row per attempt with route/model/provider/success/reason. | No durable record. |
| 5.7 | Admin is ALERTED on fallback | After 5.1, open `/admin` and `/admin/settings`. | A visible banner/count that a stage ran on a non-primary model or exhausted its pool. ⚠️ **Verify this UI was actually built — it may be incomplete.** | No surfaced alert. |

> Note: 5.1–5.3 are destructive to settings — do them in a controlled window and restore the settings afterward. Record the original values first.

---

## 6. Routing refactor REGRESSION — every inference path still works

The refactor is under **all** inference. Exercise each role once and confirm normal operation (this is the "did we break everything" check).

| # | Path | How to exercise | Expected |
|---|---|---|---|
| 6.1 | Interview / chat | Log in, ask the Oracle a normal question in chat. | A grounded answer; retrieval ran; no error. |
| 6.2 | Extraction (documents) | Upload a small text/PDF doc at Admin → Documents (or use the test image, Section 7). | Document reaches `complete`; candidates/claims appear. |
| 6.3 | Synthesis | Trigger `brain-synthesis` (Trigger MCP or admin). Prod now has **189 approved claims**, so it's unblocked. | A `brain_section_versions` row is written; narrative looks coherent. |
| 6.4 | Translation | Admin → Claims → "Translate selected for China team" on a claim (a `zh-CN` employee exists). | `claim-translation` runs; a `claim_translations` row appears. |
| 6.5 | Vision | Section 7. | Vision `model_runs` row, no fallback. |
| 6.6 | Workers | Trigger/observe at least one run each of `contradiction-watcher`, `lull-interjection`/live-recall (if testable), `taxonomy-reevaluation`. | They dispatch and complete without `No adapter`/routing errors. |
| 6.7 | Batch extraction mode | If `extraction_dispatch_mode='batch'` is ever used: submit + drain. | Batch submits, drains, promotes — no routing errors. |

**Verification queries (read-only):**
- Which model actually ran extraction/vision:
  ```sql
  select task_type, model, provider, success, error, created_at
  from model_runs
  where task_type in ('document-ingestion','document-ingestion-vision')
  order by created_at desc limit 10;
  ```
- Claim counts: `select status, count(*) from claims group by status;`

---

## 7. Image → claims END-TO-END (the original goal)

Test document: **`9d09fa89-3a46-465e-a98b-837287c9e22a`** (the "Pop Creations Flow" swimlane PNG). It is currently `failed`, 0 claims.

**Step 0 — fix the extraction model first.** Extraction is currently set to `qwen/qwen3.7-plus`, which produces loose JSON and yields 0 claims. At **Admin → Settings → Extraction model**, select **`google/gemini-3.1-flash-lite`** (in the approved pool, native strict JSON). No code change/redeploy needed (settings are read at runtime).

**Step 1 — clean + re-run the document.** From `C:\repos\oracle`:
```bash
PROD_URL="<oracle_session_pooler>" DOCUMENT_ID="9d09fa89-3a46-465e-a98b-837287c9e22a" APPLY=1 \
  node scripts/reevaluate-document.mjs
```
(That deletes the doc's prior claims/chunks/candidates and resets it to `pending_processing`; it aborts safely if any claim is in the Brain/a contradiction/a gap.) Then trigger `document-ingestion` for that `documentId` (Trigger MCP or dashboard).

**Step 2 — verify the result:**
1. **Vision ran on Qwen, no fallback:**
   ```sql
   select provider, model, error from model_runs
   where task_type='document-ingestion-vision' order by created_at desc limit 1;
   ```
   Expect `provider=qwen`, `model=qwen3-vl-235b-a22b-thinking`, `error` NULL.
2. **Claims flowed:**
   ```sql
   select c.claim_type, count(*) from claims c
   join claim_evidence ce on ce.claim_id=c.id
   join document_chunks dc on dc.id=ce.source_document_chunk_id
   where dc.document_id='9d09fa89-3a46-465e-a98b-837287c9e22a'
   group by c.claim_type;
   ```
   Expect a healthy mix dominated by `dependency` (handoff) claims, NOT 0 and NOT ~80 shallow `process_rule`.
3. **Document status is `complete`** (not `failed`, not `complete` masking an error):
   `select status, processing_error from documents where id='9d09fa89-…';`
4. **Lane/role accuracy (manual):** open the actual image; pick ~5 boxes and confirm the claims attribute them to the **correct swimlane/department**. IMPORTANT: judge against the **image** (column color + position), NOT against any model's transcription — an earlier "lane errors" finding this session was a *grading mistake* against a bad reference; Qwen's lanes were actually correct.

**PASS** = Qwen vision, claims > 0 with correct handoffs and correct lanes, document `complete`.

---

## 8. The anti-masking ("silent failure") fixes actually fire

These were added so failures can't hide. Prove each surfaces.

| # | Test | Expected |
|---|---|---|
| 8.1 | Missing provider key at boot | Worker logs `PROVIDER UNAVAILABLE: "<provider>" …` **in prod** (not suppressed). |
| 8.2 | Embedding failure during ingestion | Document ends `complete` but `processing_error` = `DEGRADED — embeddings failed…` (chunks stored without vectors are flagged, not silent). |
| 8.3 | Extraction model failure | Document marked **`failed`**, not `complete`. |
| 8.4 | Vision fallback (if it ever happens) | A `document-ingestion-vision` `model_runs` row exists and its `error` names the fallback; a loud `VISION FALLBACK` log appears. |
| 8.5 | `triggerTask` with no `TRIGGER_SECRET_KEY` (no-sweep tasks) | The admin action surfaces the failure: claim-translation throws, extraction-ab flips the row to `error`, transcripts discovery/ingest throws, brain-synthesize returns 502 (not `triggered:true`). |
| 8.6 | `graph-transcripts` first-page 404 | Logged (not silently treated as "no transcripts"). |
| 8.7 | Non-array `domains` from a model | `promotion-executor` logs the corrupt-candidate error (doesn't silently `[]`). |
| 8.8 | OpenAI batch malformed line | Logged with the bad line. |

### 8.9 Chat attachments
- Attach an **image** in chat → it's read by the model (the neutral-shape fix). Run with a vision-capable interview model.
- Attach a **PDF** in chat → KNOWN GAP: the adapters have no neutral file-part translator yet; confirm it **degrades cleanly** (no crash), but don't expect full PDF comprehension.

### 8.10 Dead-end "general/utility" picker
- Confirm `default_general_purpose_route` now drives a real internal job (e.g. taxonomy cluster-naming) — or was removed. (It was previously wired to nothing.)

### 8.11 Qwen region
- Confirm all Qwen usage (vision, extraction A/B evals, translation) authenticates via `DASHSCOPE_BASE_URL` (intl) + the prod key. A 401/`No adapter` for a Qwen route means the region/key is wrong.

---

## 9. Known NOT fixed (do not expect these to pass)

- **Message-extraction conversation batching** (`fix_claim_extr.md`): NOT implemented. `claim-extraction.ts` still selects the first 100 pending messages globally then segments, so a long same-channel discussion can split mid-thread. This is a known quality weakness, not a regression.
- **PDF/file chat attachments**: only the image shape was fixed; a neutral file-part translator is still missing.
- **Admin fallback-alert UI** (Test 5.7): verify whether it was actually built; the spec called for it but it may be partial.

---

## 10. After testing
- Restore any settings you changed for destructive tests (5.1–5.3, and the vision-slot test 5.4).
- Record results (pass/fail + evidence) and update `HANDOFF.md`.
- If extraction now works with `gemini-3.1-flash-lite`, decide whether to keep it or pursue per-claim salvage (which only becomes possible once structured-output validation is made non-throwing — see `HANDOFF.md` "REVERTED EXPERIMENTS").

---

## Appendix A — complete issue inventory (context for every test)

**Vision (Pass 1):** (1) diagrams sliced into independent extraction windows + byte-chunking severed arrow lines; (2) an image-GENERATION model used for image reading; (3) thinking-model vision output truncated (no token budget); (4) temperature 0 wrong for a thinking model; (5) DashScope downscales images.

**Image transport / adapters:** (6) image shaped for the pre-dispatch provider and pushed through `providerOptions.messages`; (7) no Qwen/DeepSeek/Google image branch; (8) silent cross-provider fallback dropped the image → fresh confabulation each run.

**Silent-failure swallows:** (9) `buildStandardAdapters` suppressed skip logs in prod; (10) vision pass unlogged + unchecked for fallback; (11) extraction failure marked `complete`; (12) embed failure → null vectors silently; (13) chunk-insert failure → text lost; (14) contradiction-watcher returned "0 contradictions" on embed failure; (15) Vertex GCS cleanup empty catch; (16) OpenAI batch dropped malformed lines; (17) promotion-executor silently `[]`'d non-array domains; (18) graph-transcripts swallowed 404; (19) chat attachments mis-shaped; (20) triggerTask callers ignored dispatch failure for no-sweep tasks; (21) resolve.ts fabricated capabilities for unknown models.

**Routing / config (the architectural root):** (22) selected Qwen routes silently fell back to a hard-coded UNAPPROVED model with no alert (key was unset); (23) wrong DashScope region (intl vs us); (24) the "general/utility" UI picker wired to nothing; (25) hard-coded model references throughout.

**Extraction conformance:** (26) extraction JSON truncated (no `maxOutputTokens`); (27) `qwen3.7-plus` loose tool-call JSON malforms fields → strict schema rejects whole window → 0 claims; (28) one bad claim nukes the whole window; the attempted salvage was unreachable because `runObject` throws on schema failure.

**Process/docs:** (29) lane accuracy was mis-judged against a bad reference (Qwen was actually correct); (30) HANDOFF carried stale items (entity registry "empty," synthesis "blocked") now corrected.

## Appendix B — quick command reference

```bash
# from C:\repos\oracle
corepack pnpm -r typecheck                              # all packages
corepack pnpm --filter @oracle/ai run verify:r2         # routing smoke (rewritten)
corepack pnpm db:migrate                                # apply migrations (incl. 78)
corepack pnpm db:check-drift                            # migration journal vs disk
corepack pnpm --filter @oracle/workers run deploy       # deploy workers (note: 'run' required)

# re-evaluate the test document (clean + reset), then trigger document-ingestion
PROD_URL="<oracle_session_pooler>" DOCUMENT_ID="9d09fa89-3a46-465e-a98b-837287c9e22a" APPLY=1 \
  node scripts/reevaluate-document.mjs
```

External IDs: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; Supabase prod `eqccjfbyrywsqkxxpjvg`; test doc `9d09fa89-3a46-465e-a98b-837287c9e22a`.
