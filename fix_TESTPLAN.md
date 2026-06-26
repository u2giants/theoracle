# Test Plan: extraction & vision MODEL BAKE-OFF + pipeline validation

Status: **READY TO EXECUTE.** Self-contained for someone with ZERO prior knowledge. Written 2026-06-26.

> ⚠️ READ THIS FIRST — INSTRUCTIONS TO THE TESTING AI SESSION ⚠️
> This is not a checklist to skim. You MUST actually run every command, capture every number, and produce EVERY deliverable in Part E **in full**. A short summary is a FAILED test. The point is an evidence-backed, side-by-side comparison of real model outputs on real production data, with scores and a defensible recommendation. If a step is blocked, say exactly why and what you tried — do not skip silently. Budget for this taking a while: ~5 extraction runs + ~2 vision runs + analysis. Do not stop early.

---

## 0. Orientation (you have no prior context — read this)

**The Oracle** is an evidence-backed enterprise knowledge graph (`pnpm`+`turbo` TypeScript monorepo). Employees upload documents/images; background jobs turn them into **claims** (operational facts) each backed by a verbatim **quote**.

A flowchart **image** is processed in **two passes**:
- **Pass 1 — VISION:** a vision model transcribes the image to faithful TEXT (persisted as `document_chunks`). Controlled by setting `default_vision_route`.
- **Pass 2 — EXTRACTION:** an extraction model reads that text and emits structured **claims** (JSON validated against a strict Zod schema). Controlled by setting `default_extraction_route`.

Repo layout you need: `apps/workers/` = Trigger.dev background jobs (incl. `document-ingestion`); `packages/ai/` = the model router + provider adapters; `packages/db/` = Postgres schema (Supabase). Deploys: workers via Trigger.dev (manual), web via Vercel (push to `main`).

**What is already confirmed working (as of 2026-06-26, do NOT re-litigate):**
- Vision on `qwen/qwen3-vl-235b-a22b-thinking` works and produces a rich transcription (~11–13k chars, ~84 one-line edges) with **no silent fallback**.
- The model-routing refactor is live: no `fallbackRouteId`, failures fail loud, the approved **pool** is the fallback chain, `enforce_model_capabilities=true`, and per-attempt records land in `model_run_attempts`.
- The extraction BLOCKER (loose-JSON Qwen → 0 claims) is resolved by using a native-strict-JSON model.

**The open question this plan answers:** *which* extraction model, and *which* vision model, give the best quality for the money. The current pick `google/gemini-3.1-flash-lite` is strict-JSON and unblocks extraction but **under-extracts badly** — it returned only **7 claims (1 dependency)** from a transcription containing **84 handoff edges**. We need a real comparison.

**The test artifact** is one document: the "Pop Creations Flow" swimlane flowchart, document id **`9d09fa89-3a46-465e-a98b-837287c9e22a`**. It has ~63 boxes across 14 swimlanes (columns = roles/departments: Albert, Buyer, Sales, Creative direction, Junior designer, Technical designers, Creative designers, Sourcing, Production, Carlos, Gina, Licensing Team, Licensor, Factories) and ~80+ directional arrows (handoffs, with conditional branch labels like "If Audit: Fail"). The IMAGE itself is the ground truth (see Appendix C).

---

## 1. The models under test

### Extraction bake-off (3 models — ALL native strict-JSON, which is required for this stage)
| Label | Settings model id (CONFIRM exact id — see §3.2) | Provider family | Why it's in the test |
|---|---|---|---|
| **M1** | `openai/gpt-4o-mini` | OpenAI | cheap baseline |
| **M2** | `google/gemini-2.5-flash` | Google Gemini | strict-JSON; earlier produced 56–81 claims on this doc as the old fallback |
| **M3** | `openai/gpt-4.1-mini` | OpenAI | newer mini, strict-JSON |

(Do NOT test Qwen for extraction — it uses loose tool-call output and malforms the schema; that failure is already documented.)

### Vision bake-off (2 models)
| Label | Settings model id (CONFIRM) | Why |
|---|---|---|
| **V1** | `qwen/qwen3-vl-235b-a22b-thinking` | current prod vision; large thinking VL model |
| **V2** | `google/gemini-2.5-flash` | the cost-appropriate Gemini *vision* (NOT image-generation) model. Rationale: diagram transcription is OCR + layout perception, not deep reasoning. Gemini **2.5 Flash** is strong at dense OCR/document understanding at low cost; **Gemini 2.5/3 Pro would be overpaying** for functionality we don't need, and **Flash-Lite/2.0-Flash risk dropping small swimlane text**. If you believe a different non-generation Gemini is a better cost/quality fit, you MAY add a third vision model V3 and justify it — but V2 must be `google/gemini-2.5-flash`. NEVER use any `*-image-*` / image-generation model for vision (that was a root-cause bug). |

---

## 2. Prerequisites & access (verify ALL before testing)

1. **Code deployed:** the refactored worker must be live. Confirm the latest Trigger.dev deploy is newer than the routing refactor; if unsure, deploy: `corepack pnpm --filter @oracle/workers run deploy` (the `run` keyword is required). Web: confirm Vercel deployed latest `main`.
2. **Migration applied:** `corepack pnpm db:migrate` (idempotent); `corepack pnpm db:check-drift` should be clean. `78_fail_loud_model_routing_settings.sql` must be applied (it adds `enforce_model_capabilities` etc.).
3. **Provider keys in prod (Trigger.dev prod env + Vercel):** `OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS_JSON` (for `google/*`), and for V1 vision `DASHSCOPE_API_KEY` + `DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. If a key is missing, the model can't run — and with the new refactor it will FAIL LOUD (it will NOT silently use another model). Verify keys exist before blaming a model.
4. **Prod DB (read + a few setting writes):** use the **session pooler** string from 1Password item *"Supabase DB Direct URL - The Oracle (CURRENT PROD …)"* → field **`oracle_session_pooler`** (the direct host is IPv6-only and won't resolve from a v4 box). Run query scripts from inside `C:\repos\oracle` so the `postgres` npm package resolves. You may also use the Supabase dashboard SQL editor / Supabase MCP for reads.
5. **Trigger.dev** access to trigger `document-ingestion` and read runs (Trigger MCP for project `proj_wgpzsvhmsopqhvwqaycn`, prod env; or the dashboard).
6. **Static gates (run first, must all pass):**
   ```bash
   corepack pnpm -r typecheck
   corepack pnpm --filter @oracle/ai run verify:r2
   corepack pnpm --filter @oracle/ai run verify:vertex-inline-image
   corepack pnpm --filter @oracle/engines run verify:r5
   corepack pnpm lint && corepack pnpm build
   ```
   Record pass/fail. Passing here does NOT prove inference works — that's the runs below.

---

## 3. Core mechanics you MUST understand before running

### 3.1 How to swap the model (no redeploy needed — settings are read at runtime)
Two settings rows in the `settings` table drive the passes:
- `default_extraction_route` — the extraction model (e.g. `"openai/gpt-4o-mini"`).
- `default_vision_route` — the vision model.

### 3.2 Capability enforcement is ON — the model must be in the approved POOL and capability-valid
`enforce_model_capabilities=true`. The resolver only uses a model for a stage if it is (a) the configured route or a member of that stage's **approved pool**, AND (b) capability-valid. So **before** selecting a model you MUST add it to the pool:
- Extraction pool: `model_pool_extraction` (currently `["google/gemini-3.1-flash-lite","qwen/qwen3.7-plus","qwen/qwen3.7-max"]`).
- Vision pool: `model_pool_vision` (may or may not be enforced for aux — verify; if vision is single-pick, just set `default_vision_route`).

**CONFIRM the exact catalog model ids first.** The picker stores `provider/modelId`. Do NOT guess. Get the real ids from the admin model picker (`/admin/settings`) OR query the catalog:
```sql
select model_id, provider, supports_structured_output, supports_vision, context_window_tokens,
       input_price_per_million, output_price_per_million
from model_capabilities
where model_id ilike '%gpt-4o-mini%' or model_id ilike '%gpt-4.1-mini%'
   or model_id ilike '%gemini-2.5-flash%'
order by model_id;
```
Use the EXACT `provider/model_id` the catalog returns. If a target model is not in `model_capabilities`, it may not be selectable under capability enforcement — note that as a finding and pick the closest catalog id.

### 3.3 The run sequence for ONE configuration (memorize — you repeat it per model)
For a given `(vision model, extraction model)` config:
```bash
# 1. Set the pool + the selection (example SQL — adapt model ids):
#    UPDATE settings SET value = '["openai/gpt-4o-mini","google/gemini-2.5-flash","openai/gpt-4.1-mini"]'::jsonb WHERE key='model_pool_extraction';
#    UPDATE settings SET value = '"openai/gpt-4o-mini"'::jsonb WHERE key='default_extraction_route';
#    (and default_vision_route as needed)

# 2. Clean + reset the test document, then trigger ingestion:
PROD_URL="<oracle_session_pooler>" DOCUMENT_ID="9d09fa89-3a46-465e-a98b-837287c9e22a" APPLY=1 \
  node scripts/reevaluate-document.mjs
#    then trigger the 'document-ingestion' task with payload {"documentId":"9d09fa89-3a46-465e-a98b-837287c9e22a"}
#    (Trigger MCP trigger_task, env=prod, or the dashboard). Wait for the run to COMPLETE.
```
`reevaluate-document.mjs` deletes the doc's prior claims/chunks/candidates and resets it to `pending_processing`; it aborts safely if any claim is in the Brain/a contradiction/a gap. The trigger then re-runs BOTH passes.

### 3.4 CRITICAL fairness caveat for the EXTRACTION bake-off
Each full reprocess re-runs vision (Pass 1), and vision is mildly non-deterministic. To compare EXTRACTION models fairly, you MUST **hold vision constant** (`default_vision_route = qwen/qwen3-vl-235b-a22b-thinking` for all three extraction runs) AND **capture each run's transcription stats** (char count + edge count, query in §A). Before comparing extraction outputs, confirm the three transcriptions are comparable (within ~15% on chars and edge count). If one run's transcription is materially different, RE-RUN that extraction config until the input is comparable, or explicitly flag the input difference in your analysis. Do not compare extraction quality across materially different inputs.

---

## 4. PART A — confirm the pipeline is live (quick smoke, ~10 min)

Run once before the bake-off. Record results.
1. With current settings, do one reprocess of the test doc (§3.3). Confirm via SQL (§A) the run COMPLETED, vision shows `provider=qwen` with NO fallback, and a `model_run_attempts` row exists for the run. If vision silently ran a different provider, STOP — the refactor/deploy is wrong.
2. Confirm the doc reached `complete` (not `failed`, not `complete`-masking-an-error: check `documents.processing_error IS NULL`).

If Part A fails, fix deploy/keys before the bake-off — comparing models on a broken pipeline is meaningless.

---

## 5. PART B — EXTRACTION BAKE-OFF (M1 vs M2 vs M3)

Vision is held at **V1 (`qwen/qwen3-vl`)** for all three. Run each extraction model in turn.

**For EACH of M1, M2, M3, do this and FILL IN the per-run record (Part E.1):**
1. Set `model_pool_extraction` to include all three test ids (once is enough), and set `default_extraction_route` to the model under test (§3.2/§3.3).
2. Reprocess + trigger; wait for COMPLETE.
3. Collect ALL of the following (SQL in §A):
   - which model/provider actually ran extraction (confirm it's the one you selected — NOT a fallback); whether any `model_run_attempts` show an advance.
   - the transcription stats for this run (chars, edge count) — for the §3.4 comparability check.
   - **claims promoted** (count), **claims by `claim_type`** (esp. how many `dependency`), **candidatesStaged**, **rejections** (from `job_runs.output_json`), and **claims RETURNED by the model** (raw_model_output claim count — to separate under-extraction from rejection).
   - input/output **tokens** + **latency** (from `model_runs`) → compute **approx cost** using the catalog pricing (§A) and **cost-per-claim**.
   - the **full list of claim summaries + their `claim_type` + the exact `exactQuote`** for this run (you will compare these qualitatively — dump them; do not summarize them away).

4. **Quality scoring (score each model 1–5 on each dimension; justify each score in 1–2 sentences with specific examples):**
   - **D1 Recall / coverage:** how many of the ~80 real handoffs did it capture as claims? (A model returning 7 claims for 84 edges scores low.)
   - **D2 Relationship richness:** fraction of claims that are `dependency`/`exception_rule` (handoffs/branches) vs flat `process_rule` ("box X exists"). Higher = better; the value of a flowchart is the arrows.
   - **D3 Correctness of attribution:** spot-check 8 claims against the IMAGE (Appendix C) — do they put each step in the RIGHT swimlane/department and state the handoff direction correctly? Count correct/total.
   - **D4 Quote fidelity:** are `exactQuote`s real verbatim spans (they must be — validation enforces it, but check they're meaningful, not trivial 2-word fragments)?
   - **D5 Schema conformance & stability:** any rejections / `requiresReview` flags / malformed-field retries? (All three are native-strict-JSON so should be clean; note any surprises.)
   - **D6 Cost & latency:** cost-per-run and cost-per-*useful*-claim, plus wall-clock.

> Run M2 (Gemini 2.5 Flash) at least **twice** to gauge run-to-run variance (extraction has some nondeterminism). Note the spread.

---

## 6. PART C — VISION BAKE-OFF (V1 qwen3-vl vs V2 gemini-2.5-flash)

Hold extraction constant at the **best extraction model from Part B** (or `google/gemini-2.5-flash` if Part B is inconclusive). Run each vision model in turn (set `default_vision_route`, reprocess, trigger).

**For EACH of V1, V2 (and optional V3), collect (SQL §A) and FILL IN Part E.2:**
- the FULL transcription text (dump `document_chunks.raw_text` joined) — you will read and compare it.
- transcription **char count**, **# of swimlane headers** captured, **# of one-line edges** (`-->` count), **# of distinct box labels**.
- vision **tokens** (input = image tokens; output) + **latency** + **approx cost** (§A).
- whether vision ran on the selected provider with NO fallback.

**Quality scoring (1–5 each, with specific evidence):**
- **VD1 Box coverage:** of the ~63 real boxes (Appendix C), how many distinct box labels appear? (count present/missing; list the missing ones.)
- **VD2 Lane/role accuracy:** pick 10 boxes; does the transcription place each in the CORRECT swimlane (judge against the IMAGE, column color + position — NOT against the other model's transcription)? Count correct/10. (Note: an earlier session WRONGLY graded Qwen here by comparing to a bad reference — Qwen's lanes were actually correct. Judge ONLY against the image.)
- **VD3 Edge/arrow capture:** how many directional handoffs + conditional branch labels ("If Audit: Fail", "Before an Order", etc.) are captured as one-line edges?
- **VD4 Fidelity / no hallucination:** any invented boxes/lanes not in the image? (A model that confabulates fails this hard.)
- **VD5 Determinism:** run the WINNER twice; how stable is the output (char/edge count, format)?
- **VD6 Cost & latency.**

**Then run the DOWNSTREAM check:** for each vision model's transcription, note how many claims the (fixed) extraction model produced from it — a better transcription should yield more/better claims. Report vision quality AND its effect on final claims.

---

## 7. PART D — (optional, destructive) verbose-fail routing tests
Only if you have a controlled window (these temporarily break a stage). Record original settings first; restore after.
- Set an extraction primary to a model whose provider key is missing, keep a working model later in the pool → confirm it AUTO-ADVANCES to the next approved model and records both attempts in `model_run_attempts` (NOT a silent hidden model).
- Make all pool models unusable → confirm `AllCandidatesFailedError` and the document is marked `failed` with that message.
- Clear `default_extraction_route` → confirm `NoConfiguredModelError`.
- Select a non-vision model for vision → confirm it's refused (capability enforcement), not used.
- Confirm any admin fallback-ALERT UI fires (verify whether it was actually built).

---

## 8. PART E — REQUIRED DELIVERABLES (this IS the test report — produce ALL of it, in full)

### E.1 Extraction comparison table (MANDATORY — fill every cell)
| Metric | M1 gpt-4o-mini | M2 gemini-2.5-flash (run a / run b) | M3 gpt-4.1-mini |
|---|---|---|---|
| Transcription chars / edges (input comparability) | | | |
| Claims RETURNED by model | | | |
| Claims promoted | | | |
| of which `dependency` / `exception_rule` | | | |
| `process_rule` (flat) | | | |
| Rejections | | | |
| Input / output tokens | | | |
| Latency (s) | | | |
| Approx cost / run | | | |
| Cost per *useful* (dependency) claim | | | |
| D1 Recall (1–5) | | | |
| D2 Relationship richness (1–5) | | | |
| D3 Attribution correctness (correct/8) | | | |
| D4 Quote fidelity (1–5) | | | |
| D5 Conformance/stability (1–5) | | | |
| D6 Cost/latency (1–5) | | | |
| **Weighted total** | | | |

Plus, for EACH model: a **2–4 paragraph written analysis** citing SPECIFIC claims it got right/wrong (quote the claim text), where it under/over-extracted, and any failure modes. Include the full claim dumps as an appendix to your report.

### E.2 Vision comparison table (MANDATORY)
| Metric | V1 qwen3-vl | V2 gemini-2.5-flash | (V3 optional) |
|---|---|---|---|
| Transcription chars | | | |
| Distinct box labels (present/63) | | | |
| Missing boxes (list) | | | |
| One-line edges captured | | | |
| Swimlane headers captured | | | |
| VD1 Box coverage (1–5) | | | |
| VD2 Lane accuracy (correct/10) | | | |
| VD3 Edge capture (1–5) | | | |
| VD4 Fidelity / no hallucination (1–5) | | | |
| VD5 Determinism (1–5) | | | |
| Input/output tokens, latency | | | |
| Approx cost / run | | | |
| Downstream claims produced (fixed extractor) | | | |
| **Weighted total** | | | |

Plus a **2–4 paragraph written comparison** with specific examples (e.g. "V2 placed 'Review Audit and send to factory' in Production, but the image shows it in Gina/white — WRONG"), and the two full transcriptions as an appendix.

### E.3 Final recommendation (MANDATORY)
- **Best extraction model** + 1 paragraph justification grounded in the table (quality vs cost; explicitly weigh "don't overpay").
- **Best vision model** + 1 paragraph justification (quality vs cost; explicitly state why the chosen Gemini tier is the right cost/quality point and Pro would be overpaying).
- The exact settings to apply the recommendation (`model_pool_extraction`, `default_extraction_route`, `default_vision_route` values).
- Any caveats (input variance, run-to-run spread, models not in catalog, keys missing).
- Restore prod settings to the recommended config (or to the original if inconclusive) and state what you left them as.

### E.4 Pipeline & routing findings (MANDATORY)
- Confirm vision/extraction ran the SELECTED models with no silent fallback (cite `model_runs` + `model_run_attempts`).
- Any anti-masking signals observed (degraded-doc notes, loud logs, etc.).
- Anything that looked wrong but you couldn't fully verify.

---

## Appendix A — SQL / query library (read-only unless noted)

Run query scripts from inside `C:\repos\oracle` (so `postgres` resolves), e.g.:
```js
// save as packages/db/_q.mjs, run: PROD_URL="<pooler>" node packages/db/_q.mjs ; then delete it
import postgres from 'postgres';
const sql = postgres(process.env.PROD_URL, { max:1, prepare:false, connect_timeout:25 });
const D = '9d09fa89-3a46-465e-a98b-837287c9e22a';
// which models ran (most recent):
console.log(await sql`select task_type,provider,model,success,error,input_tokens,output_tokens,latency_ms,created_at
  from model_runs where task_type in ('document-ingestion','document-ingestion-vision') order by created_at desc limit 6`);
// routing attempts (the new table):
console.log(await sql`select * from model_run_attempts order by created_at desc limit 10`);
// job outcome counts:
console.log(await sql`select output_json from job_runs where input_json->>'documentId'=${D} and job_type='document-ingestion' order by started_at desc limit 1`);
// claims for the doc, by type:
console.log(await sql`select c.claim_type, count(distinct c.id)::int n from claims c
  join claim_evidence ce on ce.claim_id=c.id join document_chunks dc on dc.id=ce.source_document_chunk_id
  where dc.document_id=${D} group by c.claim_type order by n desc`);
// full claim dump (summaries + quotes) for the doc:
console.log(await sql`select c.claim_type, c.summary, ce.exact_quote from claims c
  join claim_evidence ce on ce.claim_id=c.id join document_chunks dc on dc.id=ce.source_document_chunk_id
  where dc.document_id=${D} order by c.created_at`);
// transcription text + stats:
const t = await sql`select string_agg(raw_text, e'\n') t, count(*)::int chunks, sum(length(raw_text))::int chars from document_chunks where document_id=${D}`;
console.log('chunks',t[0].chunks,'chars',t[0].chars,'edges', (t[0].t.match(/-->/g)||[]).length);
// claims the model RETURNED (vs promoted): jsonb_array_length(raw_model_output->'claims') per batch
console.log(await sql`select eb.status, jsonb_array_length(coalesce(eb.raw_model_output->'claims','[]'::jsonb)) returned
  from extraction_batches eb join job_runs jr on jr.id=eb.job_run_id where jr.input_json->>'documentId'=${D}`);
// pricing for cost calc:
console.log(await sql`select model_id, input_price_per_million, output_price_per_million from model_capabilities
  where model_id ilike any(array['%gpt-4o-mini%','%gpt-4.1-mini%','%gemini-2.5-flash%'])`);
await sql.end();
```
Setting writes (use sparingly, record originals first):
```sql
-- example: select the extraction model under test (ensure it's also in the pool)
UPDATE settings SET value='"openai/gpt-4o-mini"'::jsonb WHERE key='default_extraction_route';
UPDATE settings SET value='["openai/gpt-4o-mini","google/gemini-2.5-flash","openai/gpt-4.1-mini"]'::jsonb WHERE key='model_pool_extraction';
UPDATE settings SET value='"qwen/qwen3-vl-235b-a22b-thinking"'::jsonb WHERE key='default_vision_route';
```

## Appendix B — command quick reference
```bash
corepack pnpm -r typecheck
corepack pnpm --filter @oracle/ai run verify:r2
corepack pnpm --filter @oracle/workers run deploy        # if you needed to redeploy ('run' required)
PROD_URL="<oracle_session_pooler>" DOCUMENT_ID="9d09fa89-3a46-465e-a98b-837287c9e22a" APPLY=1 node scripts/reevaluate-document.mjs
# then Trigger the 'document-ingestion' task (Trigger MCP / dashboard), env=prod, payload {"documentId":"9d09fa89-..."}, wait for COMPLETE
```
External IDs: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; Supabase prod `eqccjfbyrywsqkxxpjvg`; test doc `9d09fa89-3a46-465e-a98b-837287c9e22a`.

## Appendix C — establishing GROUND TRUTH (do this BEFORE scoring)
The IMAGE is the only valid ground truth. Open the original file (it's in Supabase storage bucket `company_documents`; the uploaded image is the "Pop Creations Flow 12112025 (1).png"). Build a reference list ONCE:
- Enumerate the 14 swimlane columns (left→right, by header + background color): Albert, Buyer, Sales, Creative direction, Junior designer, Technical designers, Creative designers, Sourcing, Production, Carlos, Gina, Licensing Team, Licensor, Factories.
- Enumerate every box and WHICH column it sits in (use the column background color + horizontal position; the columns are color-coded). Known tricky ones a prior session got WRONG by trusting a transcription: "Review Audit and send to factory" is in **Gina** (white column), and "SKUs creation" is in **Carlos** (peach column, 10th) — NOT Sourcing. So verify against the pixels, not a transcription.
- Enumerate the arrows (source box → target box, + any branch label).
Use THIS list to score VD2 (lane accuracy), D3 (attribution), and box coverage. Do not score against any model's own transcription.

## Appendix D — what is already known / out of scope
- Qwen is NOT an extraction candidate (loose tool-call JSON malforms the schema → 0 claims). Confirmed; don't re-test it for extraction.
- `gemini-3.1-flash-lite` under-extracts (7 claims/1 dependency from 84 edges) — you may include it as a 4th extraction data point for contrast, but the three named models are the focus.
- Message-extraction conversation batching (`fix_claim_extr.md`) is implemented but NOT covered here (this plan is the document/image path).
- PDF chat attachments are a known gap (no neutral file-part translator).
