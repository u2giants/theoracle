# HANDOFF — Recall.ai wiring + extraction tuning + China bilingual layer + meeting picker

Last updated: 2026-06-26. Delete this file once the remaining items below are closed.

HOW TO TRUST THIS DOC: the two blocks immediately below — "CARRIED-OVER ITEMS (re-verified)" and the diagram section's "SESSION-END STATE" — were verified against PROD on 2026-06-25 evening and are authoritative. Everything in the dated sections FURTHER DOWN is last-known from its own session and may be stale (this session caught several stale lines); re-verify against prod before acting on anything below those two blocks.

---

## Fail-loud routing + conversation-aware extraction completion — 2026-06-26

Status:
done in source, pushed, migrated, and worker-deployed.

Done:
- Committed and pushed `8e0a45c` (`feat(ai): remove silent fallbacks and preserve extraction conversations`) to `main`.
- Applied prod DB migrations/seeds against current prod Supabase `eqccjfbyrywsqkxxpjvg` using the 1Password current-prod session pooler.
- Deployed Trigger.dev prod worker version `20260626.5`.
- Reran GitHub Actions `PR check` for the pushed commit; final rerun passed.
- Implemented `fix_claim_extr.md`: sync and batch claim extraction now claim whole same-channel conversation segments and include prior same-channel complete/skipped messages only as non-quotable carry-in context.
- Verified prod settings after migration:
  - `default_extraction_route = google/gemini-3.1-flash-lite`
  - `default_general_purpose_route = qwen/qwen3.7-max`
  - `default_translation_route = qwen/qwen-mt-plus`
  - `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking`
  - `extraction_char_budget = 24000`
  - `extraction_carry_in_count = 12`
- Reconciled production Drizzle journal drift for generated migration `0007_tricky_charles_xavier.sql`: prod already had the `claim_translations` table plus `claims.source_lang` and `employees.locale`; CI expected the LF checkout hash `af12b253571b59ea7c214c978f11c21ef216bcca8e0dbe885ce61a011594cb5f`.
- Added missing local/session secrets to 1Password `vibe_coding` as Secure Notes: `Supabase Runtime Keys - The Oracle (oracle.old local .env.local)`, `OpenRouter API Key - The Oracle (local .env.local)`, `Trigger.dev Secret Key - The Oracle (local .env.local)`, and `Vercel OIDC Token - The Oracle (local .env.local)`.

Next action:
- No continuation is required for this workstream. Web deployment was not directly confirmed through Vercel CLI/MCP because local Vercel metadata was absent and the CLI status check timed out; the pushed commit's Next.js build and CI passed, and the repo's Vercel Git integration remains the expected web deploy path.

Risks / watchouts:
- Local `.env.local` still points at `oracle.old` (`vokucjpanhvqunimlvsp`). Do not run prod migrations from local env without overriding `DIRECT_URL` to the current prod 1Password session pooler.
- The migration runner hashes generated Drizzle files from the current checkout. Windows CRLF vs CI LF can surface as journal drift if a generated migration was previously recorded with a different line ending hash; reconcile only after verifying the schema objects already exist.

---

## Test plan run — 2026-06-26

Ran `fix_TESTPLAN.md` as far as current prod access/state allows.

Static gates:
- PASS: `corepack pnpm -r typecheck`
- PASS: `corepack pnpm --filter @oracle/ai run verify:r2`
- PASS: `corepack pnpm --filter @oracle/ai run verify:vertex-inline-image`
- PASS: `corepack pnpm --filter @oracle/engines run verify:r5`
- PASS: `corepack pnpm --filter @oracle/engines run verify:r7`
- PASS: direct recursive lint via `corepack pnpm -r --if-present run lint`
- PASS: direct recursive build via `corepack pnpm -r --if-present run build`
- NOTE: root `pnpm lint` / `pnpm build` still fail in this local shell because Turbo cannot find a plain `pnpm` binary; `corepack pnpm` works, but `pnpm` is not on PATH and `corepack enable` cannot write to `C:\Program Files\nodejs`.

Code fix made during testing:
- Fixed React purity lint in `apps/web/app/admin/_components/model-attempt-alert-banner.tsx` by replacing render-time `Date.now()` with SQL `now() - interval '7 days'`.

Prod prep:
- Applied prod migrations through `corepack pnpm --filter @oracle/db migrate` using the current prod session pooler from 1Password.
- Deployed Trigger worker from local source: prod worker version `20260626.1`, 21 tasks.
- WARNING: the migration runner's seed step reset model settings to legacy defaults. Restored the pre-run Qwen-oriented pools/routes, then intentionally set `default_extraction_route='google/gemini-3.1-flash-lite'` for the image test and kept it there because the test succeeded. Also corrected `default_interview_route='anthropic/claude-haiku-4-5-20251001'` so it matches `model_pool_interview`.

Live runtime results:
- PASS: no live references to `fallbackRouteId`, `DEFAULT_ORACLE_ROUTES`, or `FALLBACK_ROUTE_ID` under `packages` / `apps`.
- PASS: image document `9d09fa89-3a46-465e-a98b-837287c9e22a` re-evaluated and `document-ingestion` run `run_cmquevo9l5tc70un6px1u0xj8` completed: 3 chunks, 7 candidates, 7 promoted claims, 0 rejections. Document is `complete`, `processing_error=NULL`.
- PASS: latest vision run used `provider=qwen`, `model=qwen3-vl-235b-a22b-thinking`, success, no error. Latest extraction run used `provider=google`, `model=gemini-3.1-flash-lite`, success, no error.
- PARTIAL QUALITY: image claim mix was 4 `process_rule`, 1 `dependency`, 1 `exception_rule`, 1 `bottleneck`. This is not the dependency-dominated mix the plan hoped for, but it is no longer 0 claims and no longer ~80 shallow process-rule claims.
- PASS: document vision/extraction success attempts were recorded in `model_run_attempts`.
- PASS after config correction: `contradiction-watcher` run `run_cmquf1jks5yr80mn33f3kh7df` completed for claim `e2fa818d-c5aa-483a-afa8-43c305ad0367`.
- PASS/Loud failure: before correcting interview config, `contradiction-watcher` failed with `NoConfiguredModelError` instead of silently falling back.
- PASS/Loud failure: `claim-translation` run `run_cmquf0c885ycc0ulpsibvhupg` failed with `AllCandidatesFailedError` instead of silently falling back.

Failures / blockers found:
- FAIL: translation through `default_translation_route='qwen/qwen-mt-plus'` fails with `400 Role must be in [user, assistant]`. Likely adapter/message-shaping issue for Qwen MT, because the translation prompt uses a system block and Qwen MT rejects the resulting role shape.
- FAIL: the all-failed translation path did not write `model_run_attempts` rows, so 5.6 is not satisfied for auxiliary all-failed calls. Document success attempts do log correctly.
- FAIL/PARTIAL: capability probe temporarily set `default_vision_route='qwen/qwen3.7-plus'` and `resolveRouteCandidates(db, 'vision')` returned a candidate instead of skipping/refusing it. Either the catalog marks that model as vision-capable or auxiliary capability enforcement is too loose. The real setting was restored to `qwen/qwen3-vl-235b-a22b-thinking`.
- BLOCKED: synthesis could not be exercised as written because prod has 0 `brain_sections` rows, despite approved claims existing.
- BLOCKED/PARTIAL: taxonomy `general` picker is wired to `taxonomy-reevaluation-manual`, but prod approved claims mostly lack embeddings. Scoped run `run_cmquf23pr5voa0un6rrwvsl4t` completed without reaching cluster naming (`domainsReady=0`).
- NOT VERIFIED: interview/chat UI, admin alert banner live UI, chat image/PDF attachments, batch extraction mode, missing-key boot logs, graph 404 logging, OpenAI malformed batch-line logging. These need authenticated web/browser interaction, deliberate env breakage, or a batch fixture.

Final prod setting state after this run:
- `default_extraction_route = google/gemini-3.1-flash-lite`
- `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking`
- `default_translation_route = qwen/qwen-mt-plus` (currently failing; see above)
- `default_interview_route = anthropic/claude-haiku-4-5-20251001`
- `enforce_model_capabilities = true`

Follow-up fix run (same day):
- Fixed Qwen MT translation by folding system instructions into the first user message for `claim_translation` / `qwen-mt*` calls, because MT models reject the OpenAI `system` role. Verified `claim-translation` run `run_cmqufk37c61jk0ioh15c84xdd` completed and wrote a `zh-CN` `claim_translations` row.
- Fixed auxiliary attempt logging for translation success and all-candidates-failed paths. Verified `model_run_attempts` records `task_type='claim-translation'`, `slot='translation'`, `provider=qwen`, `model=qwen-mt-plus`, `success=true`.
- Tightened runtime capability enforcement for Qwen vision models: non-VL/non-omni Qwen catalog entries are normalized to `vision=false`. Verified `default_vision_route='qwen/qwen3.7-plus'` now raises `ModelCapabilityError` for missing `vision`; prod setting restored to `qwen/qwen3-vl-235b-a22b-thinking`.
- Fixed the Qwen catalog source to honor `DASHSCOPE_BASE_URL`, matching inference.
- Fixed seed safety: migrations still seed defaults, but existing `settings.value` is no longer overwritten on conflict. Default model settings were also updated to the current approved pools/routes.
- Seeded stable `brain_sections` for every legacy knowledge domain so synthesis has targets. Verified prod now has 17 sections; `brain-synthesis` for `domain-costing` completed as run `run_cmqufzj4m63n40hojuh7ywtf4` and wrote draft version `3b6c7f6e-9dff-42bd-ad3c-4bbda0e95dba`.
- Increased on-demand `brain-synthesis` max duration from 10 minutes to 30 minutes, matching scheduled synthesis. A larger `domain-licensing` run hit the old 10-minute cap before this change.
- Fixed taxonomy reevaluation so historical approved claims without embeddings get embedded before clustering, instead of making the general-purpose picker path unreachable. Verified run `run_cmqug5j2m6e380on6lhxixis7` wrote one model-named proposal: `operations_systems` / `Design Workflow System Management`, with successful `taxonomy-cluster-naming` attempt rows through `default_general_purpose_route`.
- Fixed Qwen JSON-object calls to include an explicit JSON instruction when DashScope requires it for `response_format=json_object`.
- Applied prod migrate/seed after the seed fixes and deployed workers through prod version `20260626.4`.

---

## CARRIED-OVER ITEMS — re-verified against prod 2026-06-25 (evening)

These supersede the older dated sections below where they conflict.

- **Synthesis demo: still NOT run, but now UNBLOCKED.** `brain_section_versions` = 0 (never run). BUT the old blocker "no approved claims to synthesize" is RESOLVED: prod now has **189 approved claims** (94 pending_review, 82 superseded, 4 rejected). So `brain-synthesis` can actually be exercised now. (Ignore older lines claiming "only one approved claim" / "no approved corpus.")
- **Entity registry: SEEDED (63 entities), 16 active top-domains.** The older "entity registry is empty -> every claim is held" note is STALE — don't repeat it.
- **China bilingual next-actions: DONE.** 6 employees set to `zh-CN`; `default_translation_route` = `qwen/qwen-mt-plus`. (Older "set an employee to 中文 / choose a translation model" actions are complete.) NOTE: the translation model is a Qwen route, so it depends on `DASHSCOPE_API_KEY` (now set) — same provider as the extraction issue.
- **Meeting-picker subject: still pending** (2 `meeting_transcripts`, 0 with `subject`). Accurate as written below.
- **Live Recall interjections: effectively OFF, but the rate cap drifted.** `teams_live_recall_min_confidence_to_post` = 101 (impossible threshold -> nothing posts), force flags all false. BUT `max_oracle_interjections_per_hour` = **3**, not the guardrail's 0. Posting is still blocked by the 101 gate, but re-clamp the rate cap to 0 if you want belt-and-suspenders (do it deliberately — a prior note says someone set it to 3).

---

## Diagram / flowchart image ingestion tuning (2026-06-25)

Status:
**END OF SESSION 2026-06-25 (evening). VISION is fixed and confirmed; EXTRACTION is blocked by a model-conformance issue; the silent-fallback refactor is now implemented in source but not yet deployed. The authoritative state is the "SESSION-END STATE" block right below — the older bullets in this section are HISTORICAL and partly WRONG (they predate the Qwen-vision fix). The "Done/blocking/Next action/Risks" bullets further down this section are now HISTORICAL — the authoritative current state is the STILL OPEN list immediately below.**

What got fixed (deployed `.2`->`.4`): wider extraction windows (24k doc / 32k image); structure-aware chunking (`chunkTextStructured`); diagram-aware + one-line-per-edge prompts; `maxOutputTokens` plumbed through all adapters; vision call sets temperature 0.6 + maxOutputTokens 32k + `highResolutionVision`; and the key fix -- PROVIDER-NEUTRAL image part at the call site with each adapter translating at dispatch (`toOpenAIImageContent`/`toAnthropicImageContent` in `cache-utils.ts`), so cross-provider fallback no longer drops the image. Qwen base URL now reads `DASHSCOPE_BASE_URL`.

### SESSION-END STATE (authoritative)

WHAT WORKS NOW:
- **Vision (Pass 1) = qwen3-vl-235b-a22b-thinking, running for real, NO fallback.** Confirmed via the new vision `model_runs` row (`task_type='document-ingestion-vision'`, `provider=qwen`, no fallback, ~17k input tokens = full-res image). The owner set `DASHSCOPE_API_KEY` in prod Trigger (intl key from 1Password `ai-provider-api-keys` -> `dashscope`); `DASHSCOPE_BASE_URL` was set to `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. Qwen base URL is env-configurable now.
- **Lane accuracy is actually GOOD.** Earlier in the session I claimed Qwen mis-assigned swimlanes — that was WRONG; I graded against a bad reference (an earlier Gemini transcription + my own misread). The owner verified against the image that Qwen's lane assignments are correct (e.g. "Review Audit and send to factory" is in Gina's white column; "SKUs creation" is in Carlos's peach column). So the "lane accuracy" problem was largely an artifact of running the Gemini FALLBACK, not Qwen. Do NOT re-open it without re-reading the actual image (column color + position), not a transcription.

THE EXTRACTION BLOCKER (doc `9d09fa89-3a46-465e-a98b-837287c9e22a` is `failed`, 0 claims):
- The selected extraction model is **`qwen/qwen3.7-plus`** (an approved pool model; pool = `["google/gemini-3.1-flash-lite","qwen/qwen3.7-plus","qwen/qwen3.7-max"]`). Qwen via the OpenAI-compatible API can't do native strict JSON-schema, so it uses a **loose tool-call** structured-output mode and **malforms fields** (scores as strings/null, domain values outside the enum, `evidence` as a non-object). The strict Zod schema rejects it, and because one bad claim fails the whole window, the run yields **0 claims** even though the Qwen transcription is perfect.
- **FAST FIX (recommended, no code):** switch extraction to **`google/gemini-3.1-flash-lite`** (already approved + native strict JSON). The Gemini fallback produced 56–81 valid claims earlier with the same schema, so a strict-JSON model should just work. The settings job brief for Extraction was updated this session to document this (strict-JSON requirement + the loose-tool-call pitfall).

THE BIG ARCHITECTURAL FINDING -> `fix_remove_fallbacks.md` (IMPLEMENTED IN SOURCE 2026-06-25; DEPLOY STILL NEEDED):
- "gemini-2.5-flash" kept appearing as the extraction model because BOTH vision and extraction were **silently falling back** to a HARD-CODED route (`vertex_gemini_2_5_flash_extraction_primary`) with reason `"No adapter registered for provider qwen"` (pre-key). Same bug as vision. The hard-coded fallback target was an UNAPPROVED model.
- Implemented source changes: no `fallbackRouteId` / hard-coded worker fallback routes; pipeline stages resolve `resolveRouteCandidates(db, slot)` and use the approved DB pool as the ordered chain; auxiliary slots (`vision`, `general`, `translation`) are explicit single-pick settings; runtime capability enforcement is gated by `settings.enforce_model_capabilities`; `model_run_attempts` records failed primary / non-primary-success attempts; Admin layout shows a recent-attempt alert; taxonomy cluster naming now consumes `default_general_purpose_route`.
- Verification run in source: `corepack pnpm -r typecheck`, `corepack pnpm --filter @oracle/ai verify:r2`, `corepack pnpm --filter @oracle/ai exec tsx src/__verify__/auxiliary-defaults.ts`, and `git diff --check` passed. Next action is commit/push/deploy the app and worker changes, then apply the new SQL migrations (`18_model_run_attempts.sql`, `78_fail_loud_model_routing_settings.sql`) through the normal Oracle migration path.

REVERTED EXPERIMENTS this session (do NOT just re-apply — investigate first):
- I added `z.coerce.number().catch(5)` to impactScore/confidenceScore and `z.enum(...).catch('general')` to domains in `extraction-system.ts`, plus a **per-claim salvage** block in `document-ingestion.ts`. **All reverted** before the final commit. Why: (a) the salvage is **UNREACHABLE** — `client.runObject` THROWS on schema-invalid output (the adapter's `tryZodParse` throws before the client's validator/`receivedJson` path is reached), so the `if (!result.validation.ok)` salvage branch never runs; (b) the `.catch` edits add `default` annotations to the model-facing JSON schema with uncertain effect on conformance, and they were band-aiding a LOOSE model (qwen3.7-plus) instead of fixing the root cause (use a strict-JSON model).
- **Recommendation:** don't band-aid the schema. Switch extraction to a native-strict-JSON model (gemini-3.1-flash-lite) — claims should flow with the plain strict schema, no catches/salvage needed. If you still want per-claim resilience, it can ONLY work AFTER the structured-output validation is made **non-throwing** (return raw output + a failure result instead of throwing) — that rework lives in the same validation path that `fix_remove_fallbacks.md` touches, so do salvage as part of / after that refactor, not standalone.
- **Investigate the environment BEFORE acting on salvage/catches next session:** (1) confirm `settings.default_extraction_route` + its `structuredOutputStrategy` (qwen=`tool_call`/loose, gemini/openai/vertex=`native_json_schema`/strict — in `resolve.ts`); (2) confirm `DASHSCOPE_API_KEY` region/account is the intended billing account; (3) trace the exact `runObject` -> `ModelRouter.generateObject` -> adapter `tryZodParse` throw-vs-return semantics (the client builds `result.validation` only if the adapter RETURNS; the adapter currently throws on a Zod failure) — this determines whether salvage is reachable at all and is the precondition for rebuilding it; (4) A/B whether the `.catch` `default` annotations actually degrade Gemini conformance before reintroducing them.

KEPT + committed this session (improvements):
- `maxOutputTokens` plumbed through the Gemini/Vertex `generateObject` paths + an `EXTRACTION_MAX_OUTPUT_TOKENS` (32k) on the extraction call — a real **truncation fix** (a dense window's claim JSON was being cut off mid-array, parsing as a bare string -> "expected object"). Independent of the reverted experiments.
- Extraction "copy job brief" text updated (strict-JSON + max-output requirement + the loose-tool-call KNOWN PITFALL).
- All the silent-failure swallow fixes + qwen vision plumbing landed earlier in commit `c50673a`.

OTHER PENDING (smaller):
- `fix_claim_extr.md` is implemented in source: sync and batch extraction now select whole same-channel conversation segments and include prior messages only as non-quotable carry-in context. `fix_resolve_ts.md` is folded into the fail-loud routing implementation: runtime capability checks now happen in `resolveRouteCandidates` when `enforce_model_capabilities=true`.
- **PDF/file chat attachments** still mis-shaped (the adapters have no neutral FILE-part translator; only image was fixed). The chat IMAGE attachment shape WAS fixed (`c50673a`).
- `default_vision_reasoning_effort` = `medium`; recommend `Low` for transcription (perception, not deliberation). Vision/extraction temperature + max_tokens are CODE constants, not admin UI.
- **Deploy discrepancy:** prod worker is `v20260625.11`, which still CONTAINS the reverted salvage/.catch (they were deployed during debugging). The committed clean source does NOT. Redeploy the worker from the committed source to align prod (keeps `maxOutputTokens`, drops salvage/.catch). Harmless functionally (salvage was unreachable, extraction is broken anyway until the model is switched), but do it for hygiene.
- `scripts/reevaluate-document.mjs` (committed) is the guarded single-doc clean+reset tool: `PROD_URL=<pooler> DOCUMENT_ID=<id> APPLY=1 node scripts/reevaluate-document.mjs`, then trigger `document-ingestion`.

Done (deployed):
- `apps/workers/src/trigger/document-ingestion.ts` changes, deployed as Trigger prod worker **`20260625.1`** (21 tasks) via the Trigger MCP `deploy` (the CLI `npx trigger.dev deploy` needs a PAT we don't have locally; the MCP is authenticated):
  - **Wider extraction windows** so a connected graph is reasoned over in one call instead of being sliced into independent ~6k windows: `MAX_DOCUMENT_TEXT_CHARS` 6k→**24k**, new `MAX_IMAGE_TEXT_CHARS` **32k** (used when `parseKind==='image'`).
  - **Structure-aware chunking** (`chunkTextStructured` + `computeStructuralBoundaries`) replaces the old byte-slice `chunkText` (deleted, with `CHUNK_OVERLAP`). Cuts only at heading/paragraph→line boundaries, never mid-line, so a flowchart arrow line is never severed. Validated invariants (contiguous, exact offsets, no severed `--(Arrow` line) with a throwaway test.
  - **Diagram-aware extraction prompt**: `looksLikeDiagramTranscription()` (detects `-->`/`--(Arrow`/`### Swimlane`) switches the image addendum to ask for handoff/branch `dependency`/`exception` claims and to quote the full `[A] --(Arrow)--> [B]` line, instead of one shallow `process_rule` per box.
- New ops tool **`scripts/reevaluate-document.mjs`** (UNCOMMITTED): guarded re-evaluation of one document — deletes its prior claims/chunks/candidates/batches/tags and resets `documents.status='pending_processing'`. DRY-RUN by default; only acts on `APPLY=1`; **aborts** if any target claim is in the Brain (`section_claims`), a contradiction, a gap, or is multi-source. Runs in one transaction. Two ordering lessons baked in: `employee_claims` is a VIEW (don't delete from it); delete `extraction_candidates` BEFORE claims (nulling `promoted_to_claim_id` in place violates `extraction_candidates_promoted_consistency_check`).

The blocking finding (the durable lesson):
- The new pipeline DID produce the right SHAPE of claims — re-ingest run `run_cmqsufh7644370uohnjafaayf` staged 15 `dependency` handoff claims (vs the old 79 one-box `process_rule`). **But all 15 failed `quote_exact_match`** → 0 promoted, so the doc went from 102 claims to **0**.
- Two causes: (1) the **vision pass is non-deterministic and was worse this run** — the transcription was 2,513 chars / 1 chunk and truncated mid-sentence (vs 12,928 chars / 4 chunks the first time), and used a format that splits each edge across two lines (node on one line, `--(Arrow)--> [target]` on the next), so no single verbatim line captures a handoff and the extractor paraphrased. (2) The first (good) run used **one self-contained line per edge**, which is exactly why its 16 dependency claims passed validation.
- **Likely root cause:** `settings.default_vision_route` in prod is `google/gemini-3.1-flash-image-preview` — an image-**generation** preview model, the wrong tool for dense visual *reading*. The shipped fallback `vertex_gemini_2_5_flash_extraction_primary` (Gemini 2.5 Flash) is a real vision model and should be more consistent.

Next action (HISTORICAL / SUPERSEDED — see "SESSION-END STATE" above. The items below date from when vision was still on the image-generation model; they are NO LONGER the plan):
1. **No-code:** change Admin → Settings → "Image vision model" off the image-generation preview to a real vision model (Gemini 2.5 Flash). Biggest reliability lever, no deploy.
2. **Code:** harden `IMAGE_TRANSCRIPTION_SYSTEM` to force **one self-contained line per edge** (never split a connection across lines) and tell extraction to set `exactQuote` to that whole edge line; optionally apply a whitespace-normalization policy to image transcriptions in the quote validator so near-verbatim edge quotes pass.
3. Re-run with `scripts/reevaluate-document.mjs APPLY=1` (doc id `9d09fa89-3a46-465e-a98b-837287c9e22a`) then trigger `document-ingestion`, and compare claim-type mix vs the baseline (79 `process_rule` / 16 `dependency` / 7 `exception_rule`).

Risks / watchouts:
- **The test flowchart `9d09fa89-3a46-465e-a98b-837287c9e22a` is currently at 0 claims** (its prior 102 were deleted). Re-running the SAME code is a coin-flip (vision non-determinism). Fix the vision model first.
- The same window/segment-splitting weakness in the MEETING/message path has been addressed in source. Deploy/apply migrations before treating prod as fixed.
- `scripts/reevaluate-document.mjs` is uncommitted — commit or discard per owner.

---

## Meeting transcript picker (2026-06-24)

Status:
done + deployed (core). Optional follow-ups remain.

Done (live in prod, `main` == deployed):
- The Oracle no longer auto-ingests meetings. Discovery (webhook + `teams-transcript-discovery-scan`) records available meetings into `meeting_transcripts` (migration `77`, prod-applied); `/admin/transcripts` is a picker where an admin chooses which to ingest. Ingesting → `teams-transcript-ingestion` writes `messages` as `pending`, anchored to real meeting time, and flips the row to `ingested`. See DECISIONS.md `D-meeting-picker` + architecture.md. Worker `v20260624.5`; commits through `38ea974`.
- Also shipped this session: claims grouped by source + shift-click range select on `/admin/claims`.

Next action (optional, not blocking):
- Populate `meeting_transcripts.subject` (and ideally participant names) — the picker has the columns but only organizer + meeting time are filled today. Subject needs an extra Graph call (`onlineMeeting` details by join id) the discovery path doesn't make yet.
- Drop the now-unused `awaiting_approval` enum value + `raw_transcripts.approval_status` columns (migrations 75/76) in a future cleanup migration — left in place because removing a PG enum value is disruptive (see `D-meeting-picker`).
- Discovery scan is on-demand only (Trigger is at the 10/10 schedule limit). If a schedule slot frees up, consider a periodic scan so the picker stays fresh without a manual "Scan for recent meetings" click.

Risks / watchouts:
- Do NOT re-introduce auto-ingest in the webhook (it must stay discovery-only). See the AGENTS.md §10 quirk on transcript ids / pull endpoint for two bugs not to reintroduce.
- `.env.local` points at `oracle.old` (`vokucjpanhvqunimlvsp`), NOT current prod (`eqccjfbyrywsqkxxpjvg`). Local `pnpm db:migrate` hits the old DB unless `DIRECT_URL` is overridden (prod connection string is in 1Password → "Supabase DB Direct URL - The Oracle (CURRENT PROD …)").

---

## China bilingual claim layer — merged to main, migration applied; worker deployed (2026-06-20)

What it is: serve the knowledge graph to a China team in Mandarin while keeping one unified brain. Full design + resolved decisions are in `china_imp.md`; AGENTS.md §7–§10 document the code surfaces.

Exact current state:
- Code is **merged into `main`** (the `docs/china-bilingual-plan` branch was integrated with `origin/main` — which had since shipped the claim-review-groups feature — resolving 12 overlapping files; typecheck + `verify:retrieval-filter-parity`/`verify:auxiliary-defaults`/`verify:mcp`/`verify:vertex-file-cache` + web build + `db:check-drift` all green before push). Vercel auto-deploys web from `main`.
- DB migration **`0007_tricky_charles_xavier.sql`** is applied to the current prod DB (`eqccjfbyrywsqkxxpjvg`). Verified after the Virginia cutover: `claim_translations` table, `claims.source_lang`, `employees.locale`, and the Drizzle journal hash now match the on-disk migration. HNSW vector index on `claim_translations.embedding` intentionally skipped (build later with `ORACLE_RUN_VECTOR_INDEXES=1`). `0007` was hand-trimmed to only the new objects — see AGENTS.md §10 "The Drizzle snapshot was baselined at migration 0007".
- The **`claim-translation` Trigger.dev worker is deployed to prod** in worker version `20260620.1`.

What is done: schema + migration; `SUPPORTED_LOCALES` in `@oracle/shared`; locale-aware `searchWithRetrievalPlan`/`buildPlanMetadataFilters` (+ extended parity guard); `source_lang` stamping at promotion; `claim-translation` worker + `translation` auxiliary model (`default_translation_route`, "copy job brief" in settings); opt-in "Translate selected for China team" bulk action + ✓ persisted badges on `/admin/claims`. **Verify ("ask someone to confirm a claim") was folded into `main`'s existing claim-review-question + review-groups feature** (`assignClaimQuestion`): the separate `claim-recertification` worker and `claim_recertification` gap type were dropped; instead `assignClaimQuestionImpl` now translates the question per recipient so a `zh-CN` recipient is asked in Chinese.

Added 2026-06-18 (committed + pushed to `main`, deploys via Vercel):
- **Employee language is now editable in the UI** — `/admin/employees` has a "Language" column (English / 中文) writing `employees.locale` via `updateEmployeeLocale` (commit `8c7fb03`). This supersedes the old "set locale by SQL" step. `employees.locale` is the single switch the bilingual layer keys off.
- **Bulk "Ask selected to evaluate"** on `/admin/claims` — tick several `pending_review` claims, pick people/groups, route them all at once (commit `cc25775`). Extracted `assignClaimQuestionCore` so the per-row form and the bulk loop share one path (recipient resolution, dedup-against-existing-assignments, per-recipient zh-CN auto translation). Per-claim failures are non-fatal (reported as skipped).

Exact next actions:
1. Set a China employee to 中文 at Admin → Employees → "Language" column (no longer SQL); choose a translation model at Admin → Settings → "Translation model" (Qwen recommended — run a small A/B vs DeepSeek per the copied brief).
2. Optionally build the discussed-but-not-built follow-ups (see AGENTS.md §15): admin side-by-side translation review.

### "Sent to review" indicator on /admin/claims — DONE (2026-06-18)

Status: **committed + pushed to `main` (commit `e5179c0`)**; deploys via Vercel.

What shipped (single file, `apps/web/app/admin/claims/page.tsx`): a `review_assignees` subselect on the claims query and a 🔁 "Sent to review" badge + assignee-name chips in the Summary cell. Source of truth is open `claim_review_question` gaps (`gaps.related_claim_ids ? claim.id`, status in `open/queued/asked`) joined to `employees.name` — NOT a column on `claims`. Renders on every status tab, so a claim sent while pending still shows reviewers after it's approved.

Verified originally against the previous Ohio prod DB; the data was migrated to current prod (`eqccjfbyrywsqkxxpjvg`) during the 2026-06-20 Virginia cutover. The subquery returned real names (72 open review gaps, 7 distinct targets) — column names, the `?` jsonb-membership operator, and the gap statuses all match live data.

Decisions made (and why): Brain synthesis stays English-only; evidence quotes are never translated (verbatim provenance); translation is opt-in per claim (cost proportional to what's directed to China); the verify/"ask to confirm" path reuses main's review-question/review-groups mechanism (no duplicate system) with the question translated per-recipient so only China recipients get Chinese.
---

## 2026-06-16 extraction A/B + employee-access update

Status:
Done. Code was committed, pushed, DB changes were applied where needed, and production web/workers were deployed.

Done:
- Fixed `/admin/ai/extraction-ab` source alignment: A/B/C model reruns now anchor to reviewed evidence quotes and do not fall back to unrelated leading document-chunk text when the quote is missing from the chunk.
- Moved extraction A/B/C reruns out of the page server action. `/admin/ai/extraction-ab` now queues rows through `claim_extraction_ab_tests.run_status`; Trigger.dev task `extraction-ab-eval` runs Gemini/Qwen and writes outputs/errors back. Migration `72_claim_extraction_ab_run_status.sql` was applied to production through linked Supabase CLI because this checkout did not have `DIRECT_URL` / `DATABASE_URL` for `pnpm db:migrate`.
- Trigger.dev worker deploy `20260616.2` succeeded after removing the attempted cron sweep. Trigger.dev was at 10/10 schedule slots, so `extraction-ab-eval` uses immediate dispatch only.
- Added Admin -> Employees Disable/Re-enable controls. They write `employees.disabled_at`; disabled employees cannot log in/link, but historical employee references remain intact.
- Production Vercel deployments were completed through commit `39c58fd Add employee access controls` before this documentation pass.

Next action:
Use Admin -> Employees for roster cleanup. For A/B/C evals, click rerun rows and let the queued worker populate results; if rows remain queued indefinitely, verify Vercel production `TRIGGER_SECRET_KEY` is a prod Trigger key and inspect Trigger.dev task runs for `extraction-ab-eval`.

Risks / watchouts:
- Do not hard-delete employees unless a separate archival/reference cleanup is designed.
- Do not move Gemini/Qwen A/B/C calls back into the page server action; multiple simultaneous rows previously hung the UI.
- Do not add another Trigger.dev schedule until the schedule limit is increased or existing schedules are consolidated.

---

## What is open and needs finishing

### 0b. 2026-06-17 dynamic model route dispatch fix

Status:
Done. Commit `fe22f19 Support dynamic model routes in router` was pushed to `main`, and Trigger.dev production worker version `20260617.1` deployed successfully with 19 detected tasks.

Done:
- Fixed `ModelRouter` so admin-selected provider/model route IDs such as `qwen/qwen3.7-plus` resolve dynamically at dispatch time instead of failing static catalog lookup with `No OracleModelRoute found`.
- Added a smoke assertion covering `qwen/qwen3.7-plus` for a `document_claim_extraction` plan.
- Verified: `corepack pnpm --filter @oracle/ai typecheck`, `corepack pnpm --filter @oracle/ai exec tsx src/__verify__/oracle-ai-client-smoke.ts`, and `corepack pnpm --filter @oracle/workers typecheck`.

Watchout:
- The failed document upload that hit the old worker may need to be retried/reprocessed; new document-ingestion runs should use worker `20260617.1`.

### 0a. 2026-06-15 local/pushed commits and review workflow

Status:
Superseded by later claim-review updates. The `training_enablement` top-domain work was committed locally as `018c2d3 Add training enablement knowledge domain`. Claim-review/revise work landed, and the review surface has since been narrowed to direct assignments plus admin-managed review groups.

Done:
- Added `training_enablement` domain, retrieval hints, boundary docs, and migration `packages/db/migrations/sql/67_training_enablement_domain.sql`.
- Implemented claim-review workflow: `/admin/claims` shows top-domain chips and supports approve/reject/revise/assign; approved-claim edits supersede the original and create a replacement in `pending_review`; `/claims` is now direct-assignment only for non-admin reviewers; `packages/db/migrations/sql/68_claim_review_workflow.sql` adds `claim_review_events` and `knowledge_domain_review_departments`.
- Added claim review groups (`/admin/claim-groups`, migration `73_claim_review_groups.sql`) so a claim-review question can be sent to multiple people or reusable groups. Group sends materialize as one `claim_review_question` gap per active employee.
- Verified locally on 2026-06-15: `corepack pnpm --filter @oracle/ai verify:retrieval-plan-domain-boundaries`, `corepack pnpm --filter @oracle/web typecheck`, `corepack pnpm --filter @oracle/db typecheck`. Browser smoke reached `/claims`, compiled the route, and redirected to login; authenticated UI was not exercised because the in-app browser had no session.

Next action:
Redeploy Vercel after claim-review UI/action changes so the new route/actions are live.

Risks / watchouts:
- The claim-review feature depends on the tables from `68_claim_review_workflow.sql`; group assignment depends on `73_claim_review_groups.sql`.
- The seeded domain-review map is retained but not currently exposed through `/claims`. Non-admin review is direct-assignment only until domain queues are intentionally restored.
- Revision intentionally supersedes the original AI claim and creates a replacement claim; do not change it into in-place edits unless the audit/provenance model is redesigned.

### 0. Current repo/deploy state (2026-06-10/11)

The working tree has two categories of uncommitted changes from before the 2026-06-15 claim-review commit:

1. Changes that were already deployed to Trigger.dev production as worker version `20260610.4` during the 2026-06-10 retrieval-backed live context session:

- `apps/workers/src/trigger/teams-live-recall-utterance.ts` — retrieval-backed live decision (prompt `teams-live-recall-1.1.0`).
- `packages/ai/src/retrieval.ts` — three runtime SQL bugs fixed in `searchWithRetrievalPlan` (see below).
- `AGENTS.md`, `docs/architecture.md`, `HANDOFF.md` — docs.

Deploy timeline this session: `20260610.1` (retrieval-backed worker), `20260610.2` (first SQL fix attempt), `20260610.3` (jsonb param binding + cause logging), `20260610.4` (final `cm.claim_id` fix — verified good). All with the normal 17 tasks.

2. Local-only fixes from the 2026-06-11 review session. These were verified locally but were **not** committed, pushed, or deployed during that session:

- `ModelRouter` now attaches actual result route metadata (`routeId`, `provider`, `modelId`, `fellBackFromRouteId`, `fallbackReason`), and chat/workers log those actual values instead of blindly logging the pre-dispatch route.
- Structured-output adapters parse invalid JSON defensively so schema problems flow through `validation.ok=false` rather than throwing before the validation result can be recorded.
- Vertex structured-output calls can cache stable + semi-stable + retrieved context and send only dynamic input live.
- Chat route no longer passes decorative Vercel AI SDK tools through `providerOptions`; retrieval runs deterministically before the model call.
- Batch submit recovery distinguishes “provider accepted but no `provider_batch_jobs` row” and resets local state for a clean tracked retry.
- Recall live utterance decisions now write `oracle_context_packs` before the model call and link usage/model-run rows even on failure.
- The previously masked lint violations in taxonomy proposal card, channel chat, document upload, chat route stale disables, and PostCSS config were fixed.

Verification from 2026-06-11: `pnpm install`, `pnpm typecheck`, `pnpm lint`, `pnpm build`, `pnpm --filter @oracle/ai verify:r2`, `verify:retrieval-filter-parity`, `verify:retrieval-plan-domain-boundaries`, `verify:vertex-file-cache`, and engine verifies `r5`, `r5.5`, `r6`, `r7`, `r9`, `r11.1` all passed.

Additional 2026-06-15 assessment of the older AI/worker diffs:
- They appear to be correctness/hardening improvements: structured provider fallback on HTTP status, stricter evidence offsets, safer embedding batching, Qwen usage normalization, worker retry/idempotency hardening, taxonomy duplicate-proposal reduction, and live interjection locking/rate re-checks.
- Package checks passed: `corepack pnpm --filter @oracle/ai typecheck`, `corepack pnpm --filter @oracle/workers typecheck`, `corepack pnpm --filter @oracle/engines typecheck`, and `corepack pnpm --filter @oracle/ai verify:retrieval-plan-domain-boundaries`.
- They are **not proven non-breaking**. Several changes affect live worker retry semantics, Recall send handling, contradiction/lull interjection transaction ordering, and synthesis/taxonomy transaction boundaries. Treat them as promising but still requiring runtime review and intentional deploy sign-off.

Do **not** assume the deployed worker, git history, and local working tree are aligned until these changes are committed/pushed and any needed Vercel/Trigger deployments are performed (commit/deploy only when Albert asks).

### 1. Demonstrate synthesis

The old Mickey/Hobby Lobby placeholder claims were hard-deleted on 2026-06-15 because they were unrelated test data. The latest `business-process.md` reprocess produced 139 real document claims in `pending_review`, but they are not approved/retrievable until reviewed. Synthesis has never been run against a real approved business-process corpus.

**You cannot meaningfully synthesize without approved real claims.** Synthesis composes a narrative across a body of related approved knowledge. Before running the synthesis demo, review/approve a coherent subset of the `business-process.md` claims and/or run real transcripts through extraction so there are several related, approved claims in the same knowledge domain. Only then is a `brain-synthesis` run a useful test.

To unblock:

1. Build up an approved-claim corpus (multiple related real claims) — approve a coherent subset of the `business-process.md` pending-review claims and/or ingest more real transcripts.
2. Trigger `brain-synthesis` via Trigger MCP or the admin UI.
3. Confirm a `brain_section_versions` row appears + narrative looks right.

### 2. Seed entity registry + active knowledge domains

On a fresh system, almost every extraction-derived claim is **held**:
- **Entity registry is empty** → new entities ("Albert H.", "Newark warehouse", "RFQ") are unresolved → claim held, entity queued as `entity_proposals`.
- **`domain_valid` fails** when the model's proposed knowledge-domains don't map to active `knowledge_top_domains`.
- **High-impact claims (≥7)** always go to `pending_review` — by design.

This is not a bug; it's the review/safety model working as intended. Get owner sign-off before loosening.

### 3. Retrieval-backed context for live Oracle — DONE (2026-06-10)

Implemented and verified in production worker `20260610.4`; expanded locally on 2026-06-11:

- `teams-live-recall-utterance` now runs the one endorsed retrieval path (`buildRetrievalPlanFromQuery` → `searchWithRetrievalPlan`, topK 5) over each utterance that passes the heuristic + cooldown/rate gates, and injects the approved claims as a `retrieved_context` prompt block (prompt version `teams-live-recall-1.1.0`).
- The 2026-06-11 local update enriches retrieved claims with quote evidence and linked Brain snippets, includes recent meeting context in the retrieval query, and records the context pack/model-run/usage linkage for the live decision.
- The decision schema gained `evidenceClaimIds`; the worker validates them against the retrieved set and stores `retrievedClaimIds` + `evidenceClaimIds` in the job output and (when a question posts) in the interjection assistant-message `metadata_json`.
- Retrieval failures degrade to the no-context prompt (with the Postgres `cause` surfaced in the warn log); they never block utterance persistence.
- The live bot still only asks clarification questions; claim IDs never appear in Teams chat text.

Verification runs (Trigger prod, synthetic `transcript.data` payloads, bot id `verify-retrieval-20260610`, channel `b3a65666-ff4c-4e0d-8ce8-11a970808f50`):

- Contradicting utterance ("keep routing all Hobby Lobby holiday decor shipping through the Newark warehouse...") → run `run_cmq8erj3y7uh70uog5qd45swt`: `retrievedClaimIds=[bdbc9918-…]`, `evidenceClaimIds=[bdbc9918-…]`, decision reason explicitly cites the approved Atlanta-DC rule, `postedQuestion=null` (clamp respected).
- Small talk ("Good morning everyone...") → run `run_cmq8es7a87qdp0hogi33nukgc`: `heuristic_skip`, no model call, no retrieval.
- `contradiction-watcher` for the approved claim → run `run_cmq8es88r7swt0hok4li3fh3p`: completes (0 contradictions) — it had been failing on the same retrieval SQL.
- All synthetic test messages in channel `b3a65666-…` were set `extraction_status='skipped'` so the extraction pipeline never treats them as real knowledge.
- The posting/metadata path (actual Recall `send_chat_message` + assistant-message evidence metadata) still needs one real live-meeting test with the user present; everything up to the post is proven.

Three runtime SQL bugs were fixed in `searchWithRetrievalPlan` / `buildPlanMetadataFilters` (`packages/ai/src/retrieval.ts`) — the hybrid query had NEVER successfully executed with domain hints before, because there were no approved+embedded claims to exercise it:

1. Bare JS arrays in drizzle ``sql`` templates expand to `($1, $2)`, so `ANY((...)::text[])` was a syntax error → list filters now bind ONE JSON-string param unpacked via `jsonb_array_elements_text` / `jsonb_to_recordset` (see new AGENTS.md §10 quirk).
2. `::vector(${EMBEDDING_DIM})` parameterized a type modifier (`vector($4)`) → now inlined with `sql.raw`.
3. `cm.id` does not exist — `claim_metadata`'s PK is `claim_id` → `timeFilter` now uses `cm.claim_id`.

The static parity guard passes unchanged (it checks filter parity between branches, not SQL validity — none of these were catchable statically).

### Fresh-developer restart packet (added 2026-06-09)

Use this subsection as the first stop for a brand-new developer. The rest of this file preserves the detailed history and evidence, but this is the current operating snapshot.

Current git/deploy snapshot:
- Latest pushed commit observed: `69cfa08 docs: add fresh developer handoff packet` on `main`.
- As of 2026-06-10 the working tree has uncommitted (but deployed) changes — see section 0 above. Re-check `git status --short --branch` before starting work.
- Trigger.dev production worker version is **`20260615.4`** (18 tasks) as of 2026-06-15 — includes the earlier Business Process domain extraction/routing work, fixes the Node 21 Supabase `ws` transport crash in document ingestion, clears stale document processing errors on successful retry, reuses existing chunk IDs on document reprocess, switches future document chunking to larger paragraph-aware chunks, and adds large-document extraction windowing plus Markdown quote normalization. Earlier `20260614.4` added nightly `model-catalog-refresh-nightly`; the one-time production run `run_cmqdsbbag23s70hoq9y3mxw4s` completed at `2026-06-14T12:52:53Z` and wrote 85 catalog rows, with partial-refresh errors for missing production `DEEPSEEK_API_KEY` and `DASHSCOPE_API_KEY`.
- `business-process.md` document `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` was reprocessed successfully in Trigger run `run_cmqehatni237e0un5ioyywuez`: 12 chunks, 155 extraction candidates, 139 claims promoted to `pending_review`, 16 rejected candidates, document status `complete`, `processing_error = NULL`. These claims are still not chat/synthesis knowledge until reviewed and approved.
- Admin Settings stage pickers now have restored "Copy job brief" text for Interview, Extraction, and Synthesis. Extraction's hard picker requirements were corrected to structured output + context >100K only; it no longer requires vision because document-image ingestion routes raw images through the auxiliary Image Vision model first, then Extraction receives text chunks.

What The Oracle can do now:
- Post-call Teams transcript ingestion through Microsoft Graph is live and validated for ad-hoc Teams calls when the Graph subscription exists before transcription starts.
- Recall.ai live Teams participation is live and validated: Recall joins the Teams meeting, streams finalized utterances to Oracle, Oracle stores them as `messages`, and Oracle can post short clarification questions back into Teams chat through Recall.
- The Teams-native app/bot wrapper is wired: users can interact with the Teams org app `The Oracle`, whose Azure Bot endpoint is `https://oracle.designflow.app/api/teams/bot/messages`.
- Native Microsoft Teams app/bot commands do not replace Recall for live audio/STT. The Teams Bot Framework wrapper is the command surface; Recall is still the live meeting media/STT transport.

What is intentionally disabled right now:
- Live Oracle interjections are clamped off in `settings`.
- Keep them clamped off unless you are running an intentional live test with the user present.
- Expected clamp values:
  - `max_oracle_interjections_per_hour = 0`
  - `teams_live_recall_min_confidence_to_post = 101`
  - `teams_live_recall_force_model_pass = false`
  - `teams_live_recall_force_post = false`
  - `teams_live_recall_disable_posting_limits = false`
- 2026-06-10 settings timeline: `teams_live_recall_disable_posting_limits` was temporarily set `true` at ~18:27 UTC for the synthetic retrieval verification and clamped back `false` at 18:35:44 UTC. Separately, `max_oracle_interjections_per_hour` was found at `3` (changed 2026-06-10 00:01:38 UTC by an unknown actor — NOT this session) and was re-clamped to `0` at 18:36:11 UTC per the guardrail above. If Albert set it to 3 intentionally, restore it deliberately.

Most important next work:
1. Run a synthesis demo by triggering `brain-synthesis` (one claim is already approved) and confirming a `brain_section_versions` row.
2. Seed/confirm entity registry and active knowledge domains so extraction does not hold ordinary claims forever.
3. One real live-meeting test (user present) of the retrieval-backed interjection posting path, confirming `evidenceClaimIds` lands in the assistant-message `metadata_json`.

Known-good live test utterance:
- Spoken: `Oracle, should artwork always go to China after licensor approval, or is Walmart an exception?`
- Expected posted question shape: `Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart an exception?`
- This path was validated through Recall chat delivery on 2026-06-09.

Operational guardrails:
- Do not rotate the shared Entra app secret without `--append`. The shared app id is `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`, and it is used by Supabase Microsoft SSO, Graph backend access, and Teams Bot Framework auth.
- Supabase Microsoft provider URL must be `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971`; do not add `/v2.0`.
- Do not paste or commit secret values. During prior debugging, secret-looking values appeared in tool output; future rotations should include any exposed Google service-account JSON, Recall webhook secret, Vercel token, and Trigger keys if policy requires cleanup.
- `supabase.exe db query --linked` may hang or hit auth circuit breakers. Stop `supabase*` processes and retry gently; do not hammer linked CLI auth.
- Vercel env writes may require CLI/API/dashboard access; the Vercel MCP is read-only in this environment.
- Trigger.dev CLI is authenticated on this Windows machine; Trigger production env is project `proj_wgpzsvhmsopqhvwqaycn`.

Before declaring future work done:
- Confirm `git status --short --branch` is clean or document any intentional uncommitted changes.
- If worker behavior changed, deploy to Trigger.dev production and record the worker version here.
- If Vercel route/env behavior changed, redeploy production and record the deployment.
- If live posting is opened for a test, clamp it off again and record the timestamp.
- If claims/synthesis state changes, record the exact DB/admin evidence.

---

## What is done (since the prior HANDOFF)

### Document ingestion: Word + image (vision), admin uploader, context/hints, auxiliary models (2026-06-14)

Committed (`d8dd2d6`, `195f9fc`, `bdb07c3`, `a2f9851`, `105addf`, `c388593`) and **deployed**: Trigger prod worker **`20260614.3`** (17 tasks) + Vercel production (auto-deploys on push to `main`). All `@oracle/*` typecheck, web ESLint, and `verify:vertex-inline-image` / `verify:vertex-file-cache` pass.

**New input formats**
- **Word (.docx)** parsed via `mammoth` (added to `apps/workers/package.json`). Old binary `.doc` still unsupported (convert to `.docx`/PDF). `resolveParseKind()` now falls back to the filename extension when the browser sends `application/octet-stream`.
- **Images (vision)** — PNG/JPEG/WebP/HEIC. Two-pass: Pass 1 = a vision model transcribes the image to faithful text; Pass 2 = that text flows through the SAME chunk → extract → quote-validate → promote pipeline. The transcription is persisted as `document_chunks`, so the quote-validation provenance guarantee holds (claims quote the transcription, never the raw image). GIF/BMP/TIFF → unsupported.
- Pass 1 prompt (`IMAGE_TRANSCRIPTION_SYSTEM`) instructs a **structured text-topology** output for diagrams/flowcharts/org charts — nodes `[Shape/Color: "label"]`, edges `[A] --(condition)--> [B]`, swimlane `### headers` — with verbatim labels kept inside the nodes so they stay exactly quotable.

**Vision is GUI-choosable, provider-agnostic**
- The Vertex adapter `buildContents`/`toVertexParts` now translate an inline `{type:'image',mimeType,data}` part into a Gemini `inlineData` part (guard: `verify:vertex-inline-image`). The worker formats the image part per provider (Gemini inlineData / Anthropic image block / OpenAI image_url) so whatever model the admin picks works. The file-backed Vertex cache path is skipped for images (a lone image is below the cache token minimum).
- **Auxiliary-model registry** (`packages/ai/src/routes/auxiliary.ts`, `AUXILIARY_MODELS`): vision + general-purpose are "auxiliary models" — single-pick selections that are NOT one of the 3 strict `OracleModelRole`s (which stay frozen). The picker, `/api/admin/models`, and `resolveAuxiliaryRouteFromSettings(db, id)` all iterate the registry. Adding the next one (e.g. audio transcription) = one registry entry + one `AUX_PRESENTATION` entry in the settings page.
- Settings: **`default_vision_route`** (+ `default_vision_reasoning_effort`). Shipped fallback `vertex_gemini_2_5_flash_extraction_primary` (Gemini — already credentialed in prod). **Seeded in prod** with `ON CONFLICT (key) DO NOTHING` (won't clobber an admin choice). Admin → Settings → "Image vision model" has a "Copy job brief" button.

**Inference vs catalog APIs** — the model dropdown reads the cached `model_capabilities` table (`GET /api/admin/models?stage=vision`), populated by `refreshModelCatalog` from direct provider list APIs + OpenRouter enrichment. Inference is always **provider-direct** (Gemini via `@google/genai`), never OpenRouter.

**Admin company-document uploader (no channel)**
- Channels can only be created by the Teams flows or the admin raw-import path — there is no "create channel" UI. So uploading company docs via a chat channel was unreachable. New: **Admin → Documents** has a multi-file drag-drop uploader → `POST /api/admin/documents` (admin-only) stores each file, inserts a `documents` row, triggers `document-ingestion`. No channel needed (the worker reads documents by id; `documents` has no channel dependency — the channel was only ever for the chat attachment message).

**Per-document context + domain hints**
- Hand-written idempotent migration `packages/db/migrations/sql/65_document_context_and_domain_hints.sql` adds nullable `documents.context` (text) and `documents.domain_hints` (jsonb), applied to prod **and** added to `schema.ts`. ⚠️ No Drizzle-generated migration accompanies the schema.ts change — the columns exist via the hand-written SQL only, so `pnpm db:check-drift` may flag them and a fresh-DB `pnpm db:migrate` will not recreate them unless the hand-written `sql/65` file is applied. Follow-up: fold into a generated migration if drift is undesirable.
- The admin uploader has a "What is this?" textarea + active-domain chips (batch-level, applied to every file in the upload). `document-ingestion` feeds `context` into BOTH the extraction prompt and the image vision prompt, and renders `domain_hints` as a non-binding prior — per-claim `domain_valid` stays authoritative.

**Not yet done / caveats**
- Vision/topology only affects images processed from now on; re-upload older images to reprocess.
- Live end-to-end image test (real upload → `complete` → claims) still pending a human upload.
- Cross-provider vision is wired but only the Vertex/Gemini path has a regression guard.
- `business-process.md` uploaded on 2026-06-15 originally failed because Trigger's Node 21 runtime needed an explicit Supabase WebSocket transport. That crash is fixed in worker `20260614.5+`, and the document row `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` was retried successfully to `status='complete'` with `processing_error=NULL`. However, the extraction attempts promoted 0 claims: the latest checked run (`run_cmqefjl0h1jif0olkl3kkpjk9`, batch `01469d78-0400-4a1e-a2fd-4f235980a94b`) staged 45 candidates, rejected 42 for strict quote mismatch and 3 for unresolved taxonomy entities. Worker `20260614.9` improves future uploads with paragraph-aware 4000-char chunks, but the existing row still has old 1500-char chunks. Re-upload the file or do a deliberate admin reprocess that recreates chunks if you want the new chunking applied to this document.

### Documentation maintenance audit from pasted task spec (2026-06-09)

Completed the broad Markdown audit requested from:

`C:\Users\ahazan2\.codex\attachments\0ddbc067-291d-421c-9a87-eaad3e2691a4\pasted-text.txt`

What was verified/updated:
- `AGENTS.md` remains canonical and now explicitly routes historical/spec docs without encouraging bulk-loading every Markdown file.
- `README.md` points new sessions to `HANDOFF.md` when present.
- `CLAUDE.md` was checked and left Claude-specific.
- Topic docs were aligned with the current live state: Graph post-call transcript ingestion is live, Recall live Teams participation is live, and Recall live posting is currently clamped off by runtime settings.
- `docs/configuration.md` now documents the live Recall safety/test settings.
- `docs/deployment.md` now has upsert-based SQL snippets to reopen and re-clamp live Recall tests.
- `.claudeignore`, `.cursorignore`, and `.copilotignore` were checked and already matched the project ignore policy.
- No secret values were added to docs.

### Teams transcript ingestion — LIVE and validated (2026-06-04/05)

- Real Meet-Now call → subscription → webhook → ingestion → **95 messages**, `speakersResolved 2/2`
- Speaker resolution by email (`fbb82cd`) + bootstrap-by-email for `@popcre.com` (`e73868b`)
- 38 employees seeded (all enabled `@popcre.com` humans)
- Two latent extraction bugs fixed: `segmentSummary` cap overflow (`71fa76f`) + broken `::uuid` cast in `stageEntityProposal` (`c159732`)
- Fuzzy quote matching for spoken transcripts (`89d2fd9`, D-transcript-fuzzy-quote)
- Raw VTT persistence (`89d2fd9`, D-raw-transcripts, hand-written `62_raw_transcripts.sql`)
- Workers deployed: Trigger.dev version **20260605.1**

### Recall.ai live Teams path — wired and deployed (2026-06-06)

The code (`bfd6612`) was committed by a prior session but was untested. This session wired it live:

- **Region bug fixed** (`4219c66`): default `RECALL_BASE_URL` was `us-west-2` but POP Creations workspace is US East. Fixed in `apps/web/lib/recall.ts`, `apps/workers/src/lib/recall.ts`, `.env.example`.
- **Vercel env vars set** (manually by user after CLI scripting issues): `RECALL_API_KEY`, `RECALL_WEBHOOK_SECRET`, `RECALL_BASE_URL=https://us-east-1.recall.ai`, `RECALL_REALTIME_WEBHOOK_URL=https://oracle.designflow.app/api/teams/live/recall`.
- **Trigger.dev env vars set** (via REST API): `RECALL_API_KEY`, `RECALL_BASE_URL`.
- **Workers deployed**: version **20260606.1** (17 tasks including `teams-live-recall-utterance`).
- **Vercel build**: `4219c66` deployed to production (READY), both verify guards passed.
- **Webhook confirmed live**: `POST /api/teams/live/recall` with no signature returns `{"error":"invalid_signature"}` — proving the route is live and `RECALL_WEBHOOK_SECRET` is loaded (if secret were missing the error would be "Recall verification secret is missing or invalid").

### Design File Operations taxonomy domain applied (2026-06-08)

Commit `616cf95` added the `design_file_operations` top-level domain, retrieval-boundary guard, seed updates, entity hints, and hand-written migration `packages/db/migrations/sql/63_design_file_operations_domain.sql`.

The local shell still could not run the normal Drizzle runner because `DIRECT_URL` / `DATABASE_URL` were unavailable. At the time, the repo was linked to the previous Ohio Supabase project and the hand-written SQL was applied through:

```
supabase.exe db query --linked --file packages\db\migrations\sql\63_design_file_operations_domain.sql --output table
```

Verification completed for:

- `entities.domain_hints`: `Google Drive`, `Illustrator`, `InDesign`, `Photoshop`, and `SharePoint` now include `design_file_operations`.
- `claim_top_domains`: backfill count for `design_file_operations` was `0` at verification time.

Follow-up verification queries against `knowledge_top_domains` started timing out after Supabase temporarily blocked linked CLI login attempts with `ECIRCUITBREAKER too many authentication failures`. Do not retry rapidly; let the pooler cool down before further linked CLI queries.

### Key lesson — TRIGGER_SECRET_KEY must be the prod key in Vercel

Vercel's `TRIGGER_SECRET_KEY` was initially a **dev** environment key. The webhook triggered `teams-transcript-ingestion` into the dev environment where no worker ran; the run expired (TTL 10m). Set Vercel Production `TRIGGER_SECRET_KEY` to the `tr_prod_…` key. See AGENTS.md §13 incident 2026-06-04.

---

## Recall.ai integration — how the pieces fit

| Component | File | Purpose |
|---|---|---|
| Bot creation | `apps/web/app/api/teams/live/start/route.ts` | Admin POST to join a meeting. Calls `createRecallLiveBot()` with `realtime_endpoints` pointing to the webhook URL. |
| Webhook receiver | `apps/web/app/api/teams/live/recall/route.ts` | Verifies `RECALL_WEBHOOK_SECRET` signature, triggers `teams-live-recall-utterance` worker. |
| Web helper | `apps/web/lib/recall.ts` | `createRecallLiveBot()` + `verifyRecallRequest()` |
| Worker helper | `apps/workers/src/lib/recall.ts` | `sendRecallChatMessage()` — posts Oracle question to meeting chat |
| Worker task | `apps/workers/src/trigger/teams-live-recall-utterance.ts` | Normalizes words → text, finds/creates channel, resolves speaker, inserts `messages` row, applies keyword gate + cooldown + rate cap, calls LLM, if confidence ≥ 70 sends chat message + inserts `oracle_interventions` row. |
| Teams-native bot | `apps/web/app/api/teams/bot/messages/route.ts`, `apps/web/teams-app/oracle/manifest.template.json` | Lets users type `@The Oracle join <link>` from inside Teams. Azure Bot + Teams channel + org app are wired; see current state below. |

**Important**: real-time webhook endpoints are per-bot, specified in `recording_config.realtime_endpoints` on Create Bot — NOT configurable in the Recall dashboard. The dashboard webhook section is for post-call lifecycle events only.

### Teams-native app/bot wrapper — wired (2026-06-09)

The Teams-native command wrapper is now wired on the platform side:

- Azure subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d` (`paygo for teams Oracle bot`)
- Resource group `rg-oracle-teams-bot`
- Azure Bot resource `theoracle-popcre-teams-bot`, SKU `F0`, single-tenant app id `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`
- Messaging endpoint `https://oracle.designflow.app/api/teams/bot/messages`
- Microsoft Teams channel enabled
- Teams organization app `The Oracle`: app id `17ccd7a1-b90b-428c-9966-33e7fb832923`, external id `850b2963-3583-4af9-bf18-84985ecbcf03`
- App availability is everyone; installed for Albert (`Albert@popcre.com`) on 2026-06-09

If the app does not appear in Teams immediately, check propagation and verify with:

```powershell
Get-M365TeamsApp -Id 17ccd7a1-b90b-428c-9966-33e7fb832923
```

Expected state: `IsBlocked=false`, `AvailableTo.AssignmentType=Everyone`, and Albert listed under `InstalledFor.InstallForUsers`.

### 2026-06-09 credential repair note

During Teams bot setup, an Entra secret rotation without `--append` temporarily broke Supabase Microsoft sign-in and invalidated the Graph backend secret. Recovery completed:

- Supabase Azure provider client secret was refreshed manually in the Supabase dashboard.
- Supabase Azure provider URL was corrected to `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971` — do **not** include `/v2.0`.
- Vercel `AZURE_GRAPH_CLIENT_SECRET`, `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, and `MICROSOFT_BOT_TENANT_ID` were refreshed and production redeployed.
- Trigger.dev prod `AZURE_GRAPH_CLIENT_SECRET` was refreshed via `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod/import` using the authenticated Trigger CLI token.

Future Entra client secrets on shared app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` must be created with `az ad app credential reset --append --display-name <purpose> ...` unless intentionally replacing every consumer.

### Current live Recall operational state

Production settings after the final 2026-06-09 test are intentionally clamped:

| Setting | Value | Why |
|---|---:|---|
| `max_oracle_interjections_per_hour` | `0` | Disables live interjections by rate cap. |
| `teams_live_recall_min_confidence_to_post` | `101` | Disables confidence-gated posting because model confidence max is 100. |
| `teams_live_recall_force_model_pass` | `false` | Restores keyword pre-gate. |
| `teams_live_recall_force_post` | `false` | Prevents blunt test echo mode. |
| `teams_live_recall_disable_posting_limits` | `false` | Restores cooldown/hourly limit enforcement. |

To test live interjections again, intentionally reopen the gates and clamp them back off afterwards:

```sql
INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('max_oracle_interjections_per_hour', '3'::jsonb, 'Hard cap per channel per hour.', now()),
  ('teams_live_recall_min_confidence_to_post', '70'::jsonb, 'Minimum live Recall model confidence required before posting.', now()),
  ('teams_live_recall_force_model_pass', 'false'::jsonb, 'Test-only: force all live Recall utterances through the model gate.', now()),
  ('teams_live_recall_force_post', 'false'::jsonb, 'Test-only: force-post Oracle test utterances.', now()),
  ('teams_live_recall_disable_posting_limits', 'false'::jsonb, 'Test-only: bypass live Recall posting cooldown and rate caps.', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = COALESCE(settings.description, EXCLUDED.description),
    updated_at = now();
```

To clamp off:

```sql
INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('max_oracle_interjections_per_hour', '0'::jsonb, 'Hard cap per channel per hour.', now()),
  ('teams_live_recall_min_confidence_to_post', '101'::jsonb, 'Minimum live Recall model confidence required before posting.', now()),
  ('teams_live_recall_force_model_pass', 'false'::jsonb, 'Test-only: force all live Recall utterances through the model gate.', now()),
  ('teams_live_recall_force_post', 'false'::jsonb, 'Test-only: force-post Oracle test utterances.', now()),
  ('teams_live_recall_disable_posting_limits', 'false'::jsonb, 'Test-only: bypass live Recall posting cooldown and rate caps.', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = COALESCE(settings.description, EXCLUDED.description),
    updated_at = now();
```

Supabase CLI note:
- `supabase.exe db query --linked` intermittently hung during this session. If it sticks, kill `supabase*` processes and retry once:

```powershell
Get-Process | Where-Object { $_.ProcessName -like 'supabase*' } |
  Stop-Process -Force -ErrorAction SilentlyContinue
```

Do not hammer retries if the linked pooler returns authentication/circuit-breaker errors.

### Recall.ai live Teams path — end-to-end tested (2026-06-08)

Real Teams meeting test succeeded:

- Admin UI `/admin/settings` start path worked.
- ElevenLabs start failed because the Recall workspace has no ElevenLabs credentials configured.
- AssemblyAI fallback succeeded; bot `68cf8eca-459d-409e-b87d-67879615b61b` joined the Teams meeting and reached `in_call_recording`.
- Recall recording `0e591d96-e63d-4f8a-84f3-5d7f4e08f277` and transcript artifact `8256d8db-97d1-4f20-b9fd-132fe621deff` were created with `assembly_ai_v3_streaming`.
- Oracle realtime endpoint `https://oracle.designflow.app/api/teams/live/recall` was configured on the bot.
- Trigger jobs `teams-live-recall-utterance` completed successfully.
- `messages` rows were inserted with `metadata_json.source='teams_live_recall'` in channel `Teams live meeting 68cf8eca-459d-409e-b87d-67879615b61b`.

No Oracle question was posted during this test because the captured utterances were skipped by the cheap heuristic gate (`decisionReason='heuristic_skip'`), which is expected for small talk / non-operational speech.

### Temporary live Recall interjection test mode — tested, clamped OFF (2026-06-08)

Worker version **20260608.2** added temporary DB-controlled test knobs for the `teams-live-recall-utterance` task. Worker version **20260608.3** made the `force_post` override safer: it now only force-posts utterances that start with `Oracle test:`.

- `teams_live_recall_force_model_pass=true` — every non-empty live utterance is sent to the interjection decision model instead of using the cheap keyword/length pre-gate.
- `teams_live_recall_force_post=true` — posts a test question even when the model returns `shouldAsk=false`; if the model gives no question, it strips an `Oracle test:` prefix and posts the remaining utterance as the question.
- `teams_live_recall_disable_posting_limits=true` — bypasses cooldown + hourly cap for live Recall interjection tests.
- `teams_live_recall_min_confidence_to_post=0` — lowers the confidence threshold for posting when the model decides `shouldAsk=true`.

This confirms whether live utterances reach the model and whether the chat-send path can be exercised. Turn this off after testing:

Result: force-post testing succeeded with ElevenLabs bot `b2c114eb-2713-44ef-8196-f776b99d0d63`. Oracle posted the test clarification back through Recall into Teams, including:

- `Should artwork always go to China after license or approval, or is Walmart seasonal an exception?`

During the first force-post test, Oracle also echoed a few follow-up utterances because `force_post=true` was intentionally blunt in version `20260608.2`. The production settings were then hard-clamped at `2026-06-08 20:33:28`:

- `max_oracle_interjections_per_hour=0`
- `teams_live_recall_min_confidence_to_post=101`
- `teams_live_recall_force_model_pass=false`
- `teams_live_recall_force_post=false`
- `teams_live_recall_disable_posting_limits=false`

Verified after the clamp: no `teams_live_recall_interjection` assistant messages were inserted after `2026-06-08 20:33:28`.

Follow-up live test on 2026-06-09:

- Fresh Teams meeting bot `4e63dc18-a63d-4cdc-a7c7-b0e967027b20` joined and recorded successfully with ElevenLabs streaming.
- Recall recording `4c0a8a18-072f-40bc-8ae9-5cfe81f0b245` and transcript artifact `050437ce-6559-4b4f-984d-ca9e2b1b2a8b` reached `done`.
- Oracle received and stored live utterances in channel `0390c592-96af-450f-aaf9-63cecae61c92`.
- Worker versions deployed during testing:
  - `20260609.1` broadened the model prompt so business-process questions asked aloud can be captured in Teams chat.
  - `20260609.2` added deterministic fallback posting for direct business-process questions when the model recognizes the need but omits a structured `question`.
  - `20260609.3` treats leading direct address (`Oracle, ...`, `Hey Oracle, ...`) as invocation, not as meta/tool chatter, before deciding whether the remaining content is a business-process question.
- Later same-link retest bot `69b0bc21-e3a0-424c-aaa0-d75c83c40567` joined and recorded successfully with ElevenLabs streaming.
- Worker version `20260609.4` changed the deterministic direct-question fallback so Oracle no longer posts an exact echo. It frames the chat message as `Can we clarify this process question: ...`.
- The `20260609.4` path fired for: `Oracle, should artwork always go to China after licensor approval, or is Walmart a seasonal exception?`
- Oracle worker job completed with no error and `postedQuestion='Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart a seasonal exception?'`.
- Recall workspace logs independently confirmed `POST /api/v1/bot/69b0bc21-e3a0-424c-aaa0-d75c83c40567/send_chat_message/ -> 200` at `2026-06-09T17:04:09.580Z` with `to='everyone'` and the same framed message.
- Follow-up direct-send probe confirmed Recall chat delivery was visible in Teams: `direct chat probe 2026-06-09 1:13pm?`.
- After the first same-link bot stopped producing live utterance jobs, the user kicked it out and a fresh bot `5f529c48-f1de-48c2-a72b-b599b53be9c4` was created for the same meeting. It reached `in_call_recording`, recording `50a40fb6-b839-44c6-8c4a-e25126f4bf19`, transcript `afda8f7d-71ab-4579-ad97-5b024fe48f68`.
- Fresh-bot hearing test succeeded: Oracle received `Oracle hearing test, 1:28 p.m..` and skipped it correctly as a technical test.
- Final business-question test succeeded: Oracle received `Oracle, should artwork always go to China after licensor approval, or is Walmart an exception?` and posted `Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart an exception?` to Teams chat.
- During the same-link rejoin, temporary worker version `20260609.5` briefly added a `recall-live-bot-create` task so Codex could create the fresh Recall bot through Trigger's production env. The file was deleted and workers were redeployed as `20260609.6` with the normal 17 detected tasks.
- Safety state after testing: temporary settings were clamped off at `2026-06-09 17:34:23` (`max_oracle_interjections_per_hour=0`, `teams_live_recall_min_confidence_to_post=101`, all force flags `false`).

To restore normal gated live interjections later, use:

```sql
UPDATE settings
SET value = '3'::jsonb, updated_at = now()
WHERE key = 'max_oracle_interjections_per_hour';

UPDATE settings
SET value = '70'::jsonb, updated_at = now()
WHERE key = 'teams_live_recall_min_confidence_to_post';
```

To keep live interjections disabled, leave those clamp values as-is. To make sure temporary force settings are off:

```sql
UPDATE settings
SET value = 'false'::jsonb, updated_at = now()
WHERE key IN (
  'teams_live_recall_force_model_pass',
  'teams_live_recall_force_post',
  'teams_live_recall_disable_posting_limits'
);

UPDATE settings
SET value = '70'::jsonb, updated_at = now()
WHERE key = 'teams_live_recall_min_confidence_to_post';
```

---

## Tooling and identifiers

- **Supabase project ref**: `eqccjfbyrywsqkxxpjvg` (`theoracle`, N. Virginia). Previous Ohio project `vokucjpanhvqunimlvsp` is now `oracle.old`. Use the linked Supabase CLI or `POST https://api.supabase.com/v1/projects/eqccjfbyrywsqkxxpjvg/database/query` with the `sbp_...` token from Windows Credential Manager (`Supabase CLI:supabase`).
  - **Direct vs pooler from a local script (2026-06-25):** the prod **direct** host `db.eqccjfbyrywsqkxxpjvg.supabase.co` now resolves to an **IPv6-only** address — a v4-only Windows box gets `ENOENT`/`getaddrinfo` and cannot connect. Use the **session pooler** instead: `postgresql://postgres.eqccjfbyrywsqkxxpjvg:<db-pw>@aws-1-us-east-1.pooler.supabase.com:5432/postgres`. Username MUST be `postgres.<ref>` (plain `postgres` → `tenant not found`), pool host prefix is `aws-1` not `aws-0` (Ohio was `aws-1-us-east-2`), and the host is region-wide (the username ref does the routing). The ready-made string is in 1Password item *"Supabase DB Direct URL - The Oracle (CURRENT PROD …)"* → field **`oracle_session_pooler`**.
- **Trigger.dev project**: `proj_wgpzsvhmsopqhvwqaycn`, prod environment. Trigger MCP (`mcp__trigger__*`) is connected.
- **Recall.ai workspace**: `f2f8cedc-6d28-4fd2-8d06-402b74d65bcc` (POP Creations), US East. Recall MCP (`mcp__recall-ai__*`) is read-only.
- **Vercel project**: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`. Vercel MCP (`mcp__vercel__*`) is read-only — env-var writes go via REST API or the Vercel dashboard.
- **Trigger.dev env var REST endpoint**: `GET/POST https://api.trigger.dev/api/v1/projects/{ref}/envvars/{env}` with PAT from `claude_desktop_config.json`.

---

## Cert material (do not commit)

`oracle-teams-cert/` is gitignored. It contains `private.pem` (in Vercel as `TEAMS_NOTIFICATION_PRIVATE_KEY`), `cert.b64.txt` (Trigger.dev as `TEAMS_NOTIFICATION_PUBLIC_CERT`), `clientState.txt`, `certId.txt`. Losing `private.pem` requires regenerating the cert and re-setting both Vercel + Trigger.dev + recreating the subscription.

---

## Risks and unknowns

- **Beta resource reliability** — `communications/adhocCalls/getAllTranscripts` is preview/flighted.
- **Subscription lapse = lost calls** — the `teams-subscription-renew` cron (`*/30`) must stay healthy; monitor `job_runs` for `teams-subscription-*`.
- **Fuzzy quote matching** relaxes the verbatim-provenance guarantee for transcripts. See DECISIONS.md D-transcript-fuzzy-quote.
- **`TEAMS_WEBHOOK_CLIENT_STATE`** must match in Vercel + Trigger.dev; the private key must pair with the worker's public cert.
