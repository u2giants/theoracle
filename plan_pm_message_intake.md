---
summary: "Open plan for reading the two project managers' Teams messages, ClickUp records and email into the Company Map at the lowest cost that still passes the quality gates: steps, gates and STATUS table."
kind: plan
status: open
read-when: working on bulk message intake (Teams chat, ClickUp, email) or on the cost of the extraction stages; read STATUS first
---

# Project-manager message intake — implementation plan

Written 2026-11-18, 3:05 PM EST, by Claude Code (edge-dev session `c9d36e3c`) for Albert Hazan.
Tracking issue: https://github.com/u2giants/theoracle/issues/607 (its checklist is the definition of done). Parent programme: #520.
Registered handoff: [HANDOFF.d/2026-11-18T1957Z-edge-dev-claude-pm-message-intake-plan.md](HANDOFF.d/2026-11-18T1957Z-edge-dev-claude-pm-message-intake-plan.md).
Sibling plan (different source, same staging idea — reuse, do not fold in): [plan_meeting_triage_pipeline.md](plan_meeting_triage_pipeline.md).
Cost analysis this plan is built on: [docs/company-map/scaledown-report-2026-11-18.md](docs/company-map/scaledown-report-2026-11-18.md).

**Who this is written for:** a lead session with no memory of the planning chat. Every step names files, behaviour and a gate. If a step forces you to invent a design, stop and record the gap in STATUS.

---

## STATUS — read this first

Fresh session starts at: **the first row marked ⬜ open, in order.** Update this table in the PR that lands a step. A row is `✅ done` only when its evidence cell names an artifact a reader can open (test path, CI run id, commit SHA, or the exact command).

| Step | Title | State | Evidence / blocker | Updated (EST) |
|---|---|---|---|---|
| A | Access probes | 🟨 Teams + ClickUp proven; email blocked | #607 opening comment (2026-11-18): ClickUp `GET /api/v2/team` 200, both managers are members; Graph `/users/{id}/chats` and `/chats/{id}/messages` 200 for both; Graph `/users/{id}/messages` 403 `ErrorAccessDenied` (no `Mail.Read` application role) | 2026-11-18 |
| 0.1 | Sizing script and cost forecast (no paid calls) | ✅ done | #607 comment 6993848642: 1,045 passages, $0.12–$0.80 forecast | 2026-11-18 |
| 1.1 | `cmap.intake_item` / `cmap.intake_thread` staging tables | 🟨 in PR | sql/036_message_intake.sql; CI runs schema test | 2026-11-18 |
| 1.2 | ClickUp collector | ⬜ open | — | — |
| 1.3 | Teams chat collector | ⬜ open | — | — |
| 1.4 | Free cleaning and thread assembly (drop-only) | ⬜ open | — | — |
| 1.5 | Thread relevance gate + triage summary (ScaleDown) | ⬜ open | — | — |
| 1.6 | Kept thread becomes a `cmap.source` (record date, no date call) | ⬜ open | — | — |
| 2.1 | Gold sample from real threads (private store) | ⬜ open | — | — |
| 2.2 | Flat-extraction bake-off on message-shaped text | ⬜ open | — | — |
| 2.3 | Relations bake-off across the four candidates | ⬜ open | — | — |
| 2.4 | Batch + cached-prefix sending path | ⬜ open | — | — |
| 2.5 | Business-area sorting with ScaleDown classify (test, adopt if it passes) | ⬜ open | — | — |
| 3.1 | Pilot: two weeks of data end to end, measured cost | ⬜ open | — | — |
| 4.1 | Full-window run + live proof | ⬜ open | — | — |
| 5.1 | Email collector | ⛔ blocked | Tenant admin consent for `Mail.Read` (application), restricted to the two mailboxes by an application access policy. No tenant-admin credential is reachable from AI sessions (same family as #593). Do not work around. | 2026-11-18 |

**Owner rulings, 2026-11-18 (second message, verbatim):** *"the oracle should read carlos' and jess' mailboxes, teams accounts (private and group chats) and our clickup."* and *"we can't afford frontier models"*. Recorded as L9 and L10; the method (ScaleDown first, then the four named models) is unchanged.
**Second opinion (2026-11-18, Muse Spark): "sound with changes".** Each point was checked against the code and folded in the same day: thread rendering and passage packing (1.6); the date call is not a saving (§6); the thread gate is conditional and calibrated (1.5); short threads are never merged and signatures are removed only by exact match (1.4); larger, unbiased gold with confidence bounds and a judge that is not a candidate (2.1, 2.3); call-shape variants and an end-to-end check (2.3); seat mechanics (2.3); caching measured before built (2.4). One point not taken as stated: HTML-to-text stays, as format conversion with the original kept (1.4).

**Decisions by Albert that bind this plan (2026-11-18, from his chat, verbatim):**
- The problem: *"it's hard to test if the Oracle system is working because we don't have enough good data in the brain for it to ask employees relevant questions for us to judge its judgement."*
- The scope and method: *"probably the project managers: Jessica and Carlos. emails, teams messages and clickup data will be a LOT (very expensive with an LLM). we need to use first scaledown.ai extract and/or scaledown.ai summarize (use /slm-agent:evaluate Skill). then use gtp-6-Luna medium batch and/or Haiku 5.5 medium batch or GLM 5.3 flash or deepseek 4.1 flash to further process. the processing must be designed to do an impeccable job with the least amount of cost for perfect performance."* (his spelling preserved; "gtp-6-Luna" = gpt-6-luna.)
- Earlier, still binding (2026-11-16): *"we need to collect WAY more information"*.

---

## 1. The ultimate goal

Today the brain knows too little about any one part of the company for anyone to judge whether the questions it asks employees are smart. **When this work is done, the brain holds a deep, evidence-backed picture of how the project-management function actually runs — who hands what to whom, what stalls, which rules people really follow — built from the two project managers' real Teams messages, ClickUp records and (once permitted) email. Albert can then read the questions The Oracle asks those two people and judge its judgement.**

Two conditions come with it, in this order: (1) the picture must be as good as the best model would produce — every fact still carries a verbatim quote and its source; (2) subject to that, the run must cost as little as possible.

**If a step in this plan conflicts with that goal, the goal wins. Stop, write the conflict into STATUS, and propose the correction.** In particular: never trade a quality gate for a lower bill; never store a summary or paraphrase as evidence; never make a paid call before the forecast in step 0.1 exists.

## 2. What this application is

**The Oracle** is POP Creations' evidence-backed company adviser. It reads company sources, builds a **Company Map** (who does what, how work flows, where hand-offs break), answers questions with sources shown, and interviews employees over Teams to fill gaps.

- Repository: https://github.com/u2giants/theoracle — **PUBLIC**. Never commit message content, names beyond what this plan already holds, mailbox addresses, tenant or app ids, LAN addresses or secrets. Fixtures are synthetic.
- `apps/brain` — Python brain: FastAPI API plus a job worker, deployed on Coolify. Postgres (Supabase) schema `cmap`; FalkorDB graph.
- `apps/web` — Next.js site on Vercel.
- Pipeline per source: `read_source → classify_extract (flat) → relations → resolve → project → process_pass → contradictions → function_assign → communities → recommend`. Job kinds and handlers: `apps/brain/brain/worker.py:37-54`.
- Models are never named in code. Each stage reads its **seat** from `cmap.model_seat` through `apps/brain/brain/seats.py:96` (`stage_model`). All chat calls go through OpenRouter via `brain/llm.py` (`post_chat_with_rescue`). ScaleDown (a provider of small task-specific models: classify, extract, compress, summarize) is called directly over HTTP from `apps/brain/brain/extract/flat.py:227`.

## 3. What triggered this work

Owner's words in the STATUS block. The interview bot is off (#518) and the map is thin; judging the bot needs one function known in depth. The owner chose the project managers and set the cost method.

## 4. Scope

**In:** collecting the two managers' Teams chats and ClickUp records for a time window; free cleaning; a cheap relevance gate; making kept threads ordinary sources; choosing the cheapest passing models for the two per-passage stages on this kind of text; a batch sending path; a measured pilot; the full run.

**NOT in this plan:**
- Email collection until the permission exists (step 5.1 stays blocked; design is included so it is a small step later).
- Teams **channel** posts (needs a different permission; chats only).
- Any other employee. Other people appear only as participants in the two managers' threads.
- Turning the interview bot on (#518) or changing interview logic.
- A review page on the website. Dropped and kept threads are listed by an admin API only (step 1.5).
- Changing model seats for documents or meetings. New seats apply to message-shaped sources only unless a separate bake-off says otherwise.
- Meeting transcripts ([plan_meeting_triage_pipeline.md](plan_meeting_triage_pipeline.md)).

## 5. Current state of the code

- **No intake exists** for ClickUp, Teams chat history or email. Nothing in `apps/brain` calls ClickUp. Graph is called only from the web (`apps/web/lib/microsoft-graph.ts`, client-credentials, `.default` scope) and from the interview code for sending.
- **Passage classification** already runs on ScaleDown: `flat.py:54` (`CLASSIFY_LABELS`), `:213` (`classify_body`), `:382` (`is_chatter`, skip at `CHATTER_SKIP_SCORE = 0.8`, `:51`).
- **Flat extraction** runs on the seated flat model (`flat.py:250` `_post_chat`); ScaleDown `/extract` is the fallback path (`:218`, `:423`).
- **Relations** — the cost centre — is one chat call per non-chatter passage: `apps/brain/brain/extract/relations.py:224` (`_post_chat`), `:431` (`_call_model`), `:839` (`handle_relations`). Windows: transcripts use `exchange_windows` (`brain/read/transcript.py:317`), everything else the anchor plus previous passages (`relations.py:193`). Every relation must carry a quote found verbatim in stored text (`:259` `find_quote`, `:293` `validate_response`).
- **Source date** costs one model call per source for documents without metadata (`document_text_date` in `brain/read/dates.py`); transcripts skip it (`:293`).
- **Transcript reader** parses a JSON list of turns with speaker, text and time (`brain/read/transcript.py:87`) or plain `Speaker: text` lines without times (labels with a clock time or more than five words are not speakers, `:174-195`); chunks one passage per speaker run (`:280`); finds a start date.
- `cmap.source.kind` is constrained to `pdf, docx, xlsx, pptx, text, image, transcript` (`apps/brain/brain/sql/001*.sql:6`).
- **No batch path.** Every call is synchronous through OpenRouter.
- Live seats on 2026-11-18: flat `z-ai/glm-5.3-flash`; relations `meta/muse-spark-1.3-contributor`; resolve, reports, recommend, grade `openai/gpt-6-luna`; answer `anthropic/claude-haiku-5.5`. Read the table, do not trust this line.
- Nothing from this plan is built. This plan, its handoff and the cost report are the only files added.

## 6. Key findings

1. **The bill is driven by calls per passage, twice** (flat, relations), plus one date call per source. Message data multiplies sources and passages, so the only large savings are (a) never sending a passage, (b) a cheaper model per passage, (c) a cheaper price for the same call.
2. **Most message text is not about how the company works.** Greetings, scheduling, "ok thanks", quoted reply chains, signatures, notifications. All of that can be removed for free or for a fraction of a cent before any chat model sees it.
3. **Each record already has its date,** so the source date is exact. (No saving: transcript sources already skip the date model call, `dates.py:293`.)
3a. **Chat is the worst shape for the current chunker.** One passage per speaker run (`transcript.py:280`) turns a back-and-forth chat into many tiny passages, each paying two model calls. Packing messages into full passages is the largest single saving in this plan.
4. **ClickUp is mostly structured.** Assignee, status, list, due date, dependencies are fields, not prose. They need formatting, not a model.
5. **Access (probed 2026-11-18, counts only):** ClickUp API key works and both managers are in the 48-member workspace. The Entra app already holds `ChatMessage.Read.All`, `Chat.ReadWrite.All`, `User.Read.All`; chat listing (41+ and 50+ chats on the first page, more pages exist) and message reads return 200. Mail read returns 403.
6. **ScaleDown summarize is a private preview** per the report. It may not be enabled on the account; step 1.5 probes it and has a fallback.
7. The ScaleDown plugin's own tool server failed to start in the planning session (package-cache error on that machine). The report was produced by running the already-installed copy of the same tool. Not a repo problem; noted so nobody hunts for it.

## 7. Approaches considered and REJECTED

| Rejected | Why |
|---|---|
| Summarise every thread with a small model and extract from the summaries | Breaks the locked evidence rule: a quote must exist verbatim in stored text. Summaries are for triage lists only. |
| Compress passages (ScaleDown compress) before relations | Same rule — compression rewrites text, and relation quotes would stop matching. Compress is already used only for answer context. |
| Send everything to the current relations seat | Correct but the most expensive option by a wide margin; the owner ruled it out. |
| Pick the cheapest model up front | Violates the bake-off method in [docs/company-map/model-stage-job-brief.md](docs/company-map/model-stage-job-brief.md): quality gates first, cost is the tiebreaker. |
| Replace relations with ScaleDown extract | Relation typing across neighbouring passages is multi-step reasoning; two earlier analyses (2026-10-27, 2026-11-03) kept it on a chat model. |
| One source per message | Explodes source count, destroys the conversational context relations need. Threads are the unit. |
| New `kind` values per system in `cmap.source` | Forces changes through every `kind` switch in the reader. Kept threads are stored as `transcript` with a separate `origin` column. |
| Route batch through OpenRouter | OpenRouter has no batch discount; discounts come from the providers' own batch interfaces. |

## 8. Design decisions

**Locked (do not relitigate):**
- L1. Evidence is verbatim. Cleaning is **drop-only** (whole lines or whole messages removed, never reworded).
- L2. A thread is dropped by the gate only when **every** slice clears a threshold that is calibrated on real message slices and is never below 0.9; anything less certain is kept. The per-passage skip at 0.8 (`flat.py:51`) stays as is.
- L3. Dropped threads stay in staging with their verdict. Nothing disappears silently.
- L4. No model id in code. New choices are seats in `cmap.model_seat`.
- L5. Quality gates before cost; grader fixed for the whole bake-off.
- L6. No paid call before the step 0.1 forecast is on the issue, and every run has a hard spend cap.
- L7. Raw message content lives only in the private database and private test store, never in the repo, issues, PRs or logs.
- L8. The four candidates for relations are the owner's list: gpt-6-luna (medium effort, batch), claude-haiku-5.5 (medium, batch), glm-5.3-flash, deepseek-4.1-flash.
- L9. **No frontier model anywhere in this pipeline** (owner, 2026-11-18: *"we can't afford frontier models"*). ScaleDown first, then only the four models in L8 — for extraction, relations, retries, gold-building, and judging. If the seated flat, relations or grade model is a frontier model, message sources must not use it; say so on #607 and seat a candidate instead. Where this plan says "reference", read "the lead-judged gold".
- L10. Sources in scope (owner, 2026-11-18): both project managers' mailboxes, their Teams chats (one-to-one and group), and the company ClickUp.

**Open (implementer's judgment, criteria given):**
- O1. Time window. Default **the last 90 days**; the pilot uses the last 14. Widen only if the 90-day map is still thin.
- O2. Conversation split for Teams chats: default a new thread after a 4-hour silence. Tune in step 1.4 on real data so threads are neither single lines nor whole weeks.
- O3. Whether ScaleDown extract or the seated flat model wins on message text — decided by step 2.2.
- O4. **Settled 2026-11-18 by the owner: one-to-one and group chats are both included** (moved to L10). Also settled the same day: the reading is not announced to the two managers.

**The pipeline, end to end:**

```
collect (free) -> clean + assemble threads (free) -> gate each thread (ScaleDown classify)
   -> [dropped: stays in staging with verdict]
   -> kept: 2-sentence triage summary (ScaleDown summarize, never evidence)
   -> stored as a transcript-kind source, date taken from the records
   -> flat extraction (winner of 2.2) -> relations (winner of 2.3, batched, cached prefix)
   -> failed validations retried once on the next-cheapest passing candidate (never a frontier model, L9) -> rest of the normal pipeline
```

Cost levers in order of size: fewer, fuller passages (packing short messages, step 1.6); drop before paying (cleaning, the existing 0.8 skip, and the thread gate if it earns its keep); fewer calls per passage (step 2.3 variants); cheapest passing model per passage; batch price; escalate only failures. Not a lever: the date call (transcript sources never make one).

## 9. The plan

### Phase 0 — know the size before spending

**0.1 Sizing script and forecast.** `lead-only` (reads private data; sets the budget).
- Add `apps/brain/brain/intake/sizing.py` with `python -m brain.intake.sizing --days 90`. It pages ClickUp and Graph for the two managers, counts records, threads (using the step 1.4 rules, imported once they exist; until then message counts) and tokens (`brain/read/chunk.py:35` `count_tokens`), and prints counts only — never text.
- Resolve the two people at run time from `cmap` directory rows by first name plus the project-manager title; fail loudly if either match is not exactly one.
- Output: a table of records / threads / tokens per system, the share removed by each free rule, and a cost forecast per candidate using current list prices fetched from OpenRouter's models endpoint and the providers' batch price pages (look these up; do not use remembered prices).
- Gate: the forecast is posted as counts and dollars on #607; a `BRAIN_INTAKE_MAX_USD` setting exists in `brain/config.py` and the pilot refuses to start without it.

### Phase 1 — collect and clean for free

**1.1 Staging tables.** `lead-only` (schema).
- New idempotent `apps/brain/brain/sql/0NN_intake.sql` (take the next free number at the time; check `ls apps/brain/brain/sql` and open PRs).
- `cmap.intake_item`: `id`, `origin` (`clickup` | `teams_chat` | `email`), `external_id`, `thread_key`, `author_ref`, `sent_at timestamptz`, `body_text`, `raw jsonb`, `content_hash`, `drop_reason text null`, `collected_at`; unique `(origin, external_id)`.
- `cmap.intake_thread`: `id`, `origin`, `thread_key`, `title`, `started_at`, `ended_at`, `item_count`, `token_count`, `gate_scores jsonb`, `verdict` (`pending` | `kept` | `dropped`), `summary text null`, `source_id uuid null`, `updated_at`; unique `(origin, thread_key)`.
- `ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS origin text, ADD COLUMN IF NOT EXISTS external_ref text`.
- Gate: `tests/test_schema.py` extended and green; migration applied twice in a row without error on the test database.

**1.2 ClickUp collector.** `helper-ok` — stop and ask if the API shape differs from what is written here or a call needs a scope the key lacks.
- `apps/brain/brain/intake/clickup.py`: ClickUp API v2, key from env `CLICKUP_API_TOKEN` (new; add to `brain/config.py` and `docs/configuration.md`). For each manager: tasks they are assigned to, created or commented on, updated inside the window (`GET /team/{id}/task` with `assignees[]`, `date_updated_gt`, `include_closed=true`, `subtasks=true`, paged), then each task's comments.
- One thread per task. First item is a header turn from speaker `ClickUp` built from fields only, **each field value copied character for character** (no re-casing, trimming or rewording), one field per line: task name, list, status, assignee, due date, dependencies. Then the description and each comment as its own turn with author and timestamp. Rendering into turns follows step 1.6.
- Respect rate limits (honour `X-RateLimit-Reset`, back off on 429). Upsert by `(origin, external_id)`.
- Gate: `tests/test_intake_clickup.py` green against recorded synthetic fixtures; a dry run prints item and thread counts that match step 0.1 within 2%.

**1.3 Teams chat collector.** `helper-ok` — stop and ask on any 403 or if paging returns duplicates.
- `apps/brain/brain/intake/graph_chats.py`: token as in [plan_meeting_triage_pipeline.md](plan_meeting_triage_pipeline.md) step 0.3 (share one Graph client module; if `brain/meetings/graph_ms.py` exists, import it; if not, create `brain/graph_ms.py` and note it in that plan's STATUS). `GET /users/{id}/chats` (follow `@odata.nextLink`), then `/chats/{id}/messages` newest first, stopping at the window edge.
- Skip `messageType != "message"`, deleted messages, and messages from applications (including The Oracle's own bot).
- Gate: `tests/test_intake_graph_chats.py` green on synthetic fixtures including paging, a 429 with `Retry-After`, and a deleted message; dry-run counts match step 0.1 within 2%.

**1.4 Free cleaning and thread assembly.** `lead-only` (decides what evidence survives).
- `apps/brain/brain/intake/clean.py`, pure functions, no network:
  - HTML to text (tags stripped, entities decoded, mentions kept as names). This is format conversion, the same kind the document readers do; the converted text is what is stored and what quotes are checked against, and the original is kept in `raw`. The drop-only rule applies from this point on.
  - Drop whole lines that are quoted reply history (`>` prefixes, `From:/Sent:/To:/Subject:` blocks, "On … wrote:"), signatures after a `-- ` line or a recognised sign-off block, legal disclaimers, and tracking boilerplate.
  - Drop whole messages that are: empty after cleaning; a reaction or single emoji; an automated notification (no-reply senders, calendar invitations and responses, ClickUp/Teams system notices); exact duplicates by `content_hash`.
  - Drop whole messages matching a secret pattern (password, key or token shapes) with `drop_reason = 'secret'` and blank the stored `body_text` and `raw` for that row; the rendered thread keeps a marker turn (`[message removed]`, author and time kept) so the order of the conversation stays intact.
  - Signatures and sign-offs are removed only by an exact allowlist built from the two managers' real signature blocks (kept in the private store), never by a loose pattern — a loose rule can delete a line stating someone's role.
  - Every drop records `drop_reason`. No function may alter the characters of a kept line.
- Thread assembly: ClickUp one per task; Teams one per chat per conversation (rule O2); email (later) one per `conversationId`. Threads shorter than 40 tokens after cleaning are dropped as `too_short`, never merged into a neighbour — merging unrelated conversations invents links between them.
- Gate: `tests/test_intake_clean.py` proves, for every fixture, that each kept line is a byte-identical substring of the input (the drop-only property) and that every adversarial row in §9a passes.

**1.5 Thread gate and triage summary.** `lead-only`.
- **Build the gate only if step 0.1 and a 200-thread probe show it pays:** it costs one ScaleDown call per slice, and if most threads are kept it adds cost and saves nothing (the per-passage 0.8 skip already catches small talk). Build it when the probe predicts at least 30% of thread tokens would be dropped; otherwise mark this row "not needed" in STATUS with the numbers and keep only the summary and listing parts below.
- `apps/brain/brain/intake/gate.py`: split a thread into slices of at most 1,500 tokens on message boundaries; call ScaleDown `/classify` once per slice with `flat.classify_body` (same labels, `"reasoning": false`); store scores in `gate_scores`. Verdict `dropped` only if **every** slice clears the drop threshold (L2); else `kept`. The labels were tuned on 400-token document passages, so **calibrate the threshold on message slices** with the gold threads: the lowest threshold at which no gold thread containing a relation is dropped, and never below 0.9.
- For kept threads call ScaleDown summarize with the instruction "Two sentences: what work this conversation is about and what was decided or is stuck." Store in `intake_thread.summary`. First probe the endpoint once; if the account lacks access (non-200), leave `summary` null, record that on #607, and continue — the summary is a convenience, not a dependency.
- Admin API `GET /intake/threads?verdict=` in `apps/brain/brain/api/` (admin only, same auth as other admin routes) returning title, dates, counts, verdict, scores, summary — no body text.
- Gate: `tests/test_intake_gate.py` (mocked ScaleDown) covers kept, dropped, mixed-slice, ScaleDown outage (thread stays `pending`, never auto-kept or auto-dropped), and summarize-unavailable.

**1.6 Kept thread becomes a source.** `lead-only` (touches the main pipeline).
- `apps/brain/brain/intake/ingest.py`: store the cleaned thread through `brain/storage.py` as a `transcript` source with `origin` and `external_ref` set. **Render it as the JSON turn list the reader already accepts** (`transcript.py:87` `_turn_from_object`: `speaker`, `text`, `timestamp` per message), not as `Name [time]: text` lines — the speaker-line parser rejects any label containing a clock time or more than five words (`transcript.py:174-195`) and never keeps a time, so timestamped lines would be glued onto the previous turn.
- **Pack short messages.** `chunk_turns` (`transcript.py:280`) makes one passage per speaker run, so a chat of one-line messages becomes dozens of 10-50-token passages, each paying a flat call and a relations call whose fixed prompt dwarfs the content. For sources with an `origin`, pack consecutive messages (speaker names kept inline, a message never split) up to the normal 400-token passage size. Passage text must stay byte-identical to stored text so quotes still validate.
- Source date: set from `started_at` via `set_source_date` in `brain/read/dates.py`. This is for correctness, not savings — transcript sources already skip the date model call (`dates.py:293`).
- Re-collection of a thread that gained messages creates a new version through `brain/versions.py`, not a duplicate source.
- New job kinds `intake_collect`, `intake_gate`, `intake_ingest` registered in `worker.py:37`; a `maybe_queue_intake` sweep in the style of the existing hourly sweeps, **disabled unless `BRAIN_INTAKE_ENABLED=true`**.
- Gate: `tests/test_intake_ingest.py` — a synthetic thread yields one source, correct date, zero date-model calls (assert the mock was not called), and re-ingest yields a version, not a second source.

### Phase 2 — choose the cheapest models that pass *(context cut point: start a fresh session here)*

**2.1 Gold sample.** `lead-only`.
- Draw **200** kept threads stratified by origin and length from the pilot window (50 for tuning, 150 for scoring); store them only in the private test store on edge-dev3 (see §12), never in git. Report every bake-off rate with a 95% confidence interval and require the **lower bound** to clear the gate; if 150 threads cannot separate two candidates, enlarge the set rather than pick by noise.
- Gold must not favour any one model: produce candidate relations from **all four candidates** (L8), pool and shuffle them without model labels, and have the lead judge each against its quote; a second, different candidate family re-judges a random 20% and the lead settles disagreements. Record counts of corrections by type. The current relations seat takes part only if it is not a frontier model (L9).
- Produce reference output by running the current relations and flat seats; then the lead reviews every reference relation against its quote and corrects the set by hand. Record the count of corrections. This corrected set is the gold.
- Gate: gold file exists in the private store with a manifest (thread ids, counts, hash) and the manifest hash is on #607.

**2.2 Flat-extraction bake-off.** `lead-only`.
- Candidates: seated flat model; ScaleDown `/extract` with the current entity spec; ScaleDown `/extract` with a spec tuned by the `slm-agent:optimize` skill on a 20-thread tuning split (never the 40 scoring threads).
- Measure mention recall and precision against gold. **Gate to pass:** recall ≥ 97% of the seated model's recall and precision not lower. Cheapest passing candidate wins; if ScaleDown passes, add a seat value that selects it for `origin IS NOT NULL` sources.
- Gate: results table (numbers only) committed to `docs/verification/` and linked from STATUS.

**2.3 Relations bake-off.** `lead-only`.
- Candidates: L8's four, each at the effort the owner named, same prompt (`apps/brain/brain/prompts/relations.md`), temperature 0. Scoring is a small new script, `apps/brain/brain/intake/bakeoff.py`, that compares each candidate's validated relations with gold (`brain/eval` grades answers, not relations, so it is used only for the end-to-end check below). **The judge of correctness must not be a candidate:** the live grade seat is one of the four, so judge with the reference relations model, or prove on 30 items that the grade seat shows no preference for its own output.
- **Call-shape variants, each measured on the same gold and adopted only if every gate still passes:** (a) skip the relations call when the passage has fewer than two mentions from the flat stage (today only chatter with no mentions is skipped, `relations.py:858`) and count what is lost; (b) one joint flat-plus-relations call for threads under about 400 tokens; (c) wider context (4-6 turns, or 800-1,200 tokens) against today's two-turn window (`transcript.py:317`), judged on recall as well as cost because decisions in chat often span many messages; (d) dropping near-identical recurring threads (automated digests and the like) beyond exact duplicates — whole threads only, and only when the lead confirms the group is machine-generated.
- **End-to-end check before seating:** build the map from the scoring threads with the winner and with the reference, ask the same 15 questions through `brain/eval`, and require the winner's grade to be no lower.
- Measure: (a) share of relations whose quote validates (`validate_response`); (b) grader-judged correctness of validated relations; (c) recall against gold; (d) truncation and malformed-JSON rate; (e) measured cost per 1,000 passages at sync and batch prices.
- **Gates to pass, all four, measured against the lead-judged gold:** correctness at least 95%; recall at least 90% of gold relations; quote validation at least 98%; truncation at most 1% (each by the lower confidence bound, step 2.1). Among passers the lowest measured cost wins. If none passes, try the cheapest candidate with its failed passages retried on the best-scoring other candidate and count the blended cost. If no single candidate or pair passes, **stop and report on #607 with the numbers; do not fall back to a frontier model (L9).**
- Gate: results table in `docs/verification/`; the winning model is selectable for message sources. `seats.py:22` `STAGES` is a fixed list and an unknown stage raises, so either add a `relations_messages` stage (extend `STAGES`, seed the row in the step 1.1 SQL file style, mind the seat cache) or keep stage `relations` and choose the model by source `origin` — whichever touches less. `tests/test_model_seats.py` extended.

**2.4 Batch and cached-prefix path.** `lead-only`.
- Only if the 2.3 winner's provider offers a batch interface (check the provider's current documentation; do not assume). Add `apps/brain/brain/llm_batch.py`: submit a job's passages as one batch, poll from the worker with backoff, map results back by passage id, then run the unchanged `validate_response`. Provider key from a new env var documented in `docs/configuration.md`; a missing key falls back to the synchronous path with a logged warning.
- Prompt caching: the relations template (`relations.py:206` `build_prompt`) already starts with fixed text, and the mention list and context vary per call, so the cacheable share may be small. **Measure the cache-hit share on a 100-passage run first**; restructure the prompt only if the measured saving is worth it, and if you do, re-run the 2.3 scoring set and confirm the gates still pass.
- A direct provider path needs a provider key and a change to provider resolution in `brain/llm.py`; OpenRouter gives no batch discount.
- Gate: `tests/test_llm_batch.py` (mocked provider: success, partial failure, expiry, duplicate result ids); a 100-passage live batch on gold costs within 10% of the forecast batch price.

**2.5 Business-area sorting with ScaleDown classify (owner ruling 2026-11-18: "yes").** `lead-only` (changes how every passage is scoped for answers).
- Today each passage is sorted into up to three of the company's business functions (`cmap.function`, 13 seeded) by one paid chat call on the flat seat (`apps/brain/brain/function_assign.py:127-147`, prompt `prompts/function_assign.md`, at most three picks `:48`). On message volume that is a third paid call per passage.
- Test replacing that call, for message sources, with ScaleDown `/classify`: labels are the active rows of `cmap.function` (name = key, rubric = description plus aliases, loaded at run time by `load_functions` `:63` so an owner edit on the functions page changes the labels with no code change), `"reasoning": false`. Take every label scoring above a threshold, strongest three, score as weight. Keep `merge_priors` (`:180`) and the company-wide fallback exactly as they are.
- Where the kind-of-content classify call (`flat.classify_body`) and this one can share a request, send one; otherwise two ScaleDown calls still replace a paid model call.
- Gold: on the step 2.1 threads the lead marks the correct functions per passage (pooled, unlabelled picks from the current method and ScaleDown, same procedure as 2.1).
- **Gates, by the lower confidence bound:** at least 90% of passages have their main function right; at least 85% of all gold functions are found; no more than 10% of picks are wrong. Calibrate the threshold on the 50 tuning threads only. Then re-run `tests/test_answer.py::test_scoped_answer_excludes_other_functions` and the 15-question end-to-end check from 2.3 and require no drop.
- If it passes: add the ScaleDown path in `function_assign.py` behind a setting, used for sources with an `origin`; the existing path stays for documents and as the automatic fallback when ScaleDown fails three times (same rule as `flat.py`). If it fails: keep the current call but on the 2.3 winner rather than any frontier model (L9), and record the numbers on #607.
- Tests: `tests/test_functions.py::test_scaledown_labels_built_from_function_table`, `::test_scaledown_scores_become_weights_top_three`, `::test_scaledown_failure_falls_back_to_model`, `::test_priors_still_apply_on_scaledown_path`.
- Gate: results table in `docs/verification/`; the tests above green; measured cost per 1,000 passages before and after on #607.

### Phase 3 — pilot *(cut point)*

**3.1 Pilot.** `lead-only`.
- Enable intake on production for the 14-day window with `BRAIN_INTAKE_MAX_USD` set from the forecast. Run to completion through `recommend`.
- Record: threads collected / dropped by rule / dropped by gate / kept; passages skipped at 0.8; calls and dollars per stage; cost per kept thread; quote-validation rate; 20 randomly sampled **dropped** threads reviewed by the lead for wrongly dropped process content (target: zero; any miss lowers nothing automatically — raise it in STATUS and adjust the rule that caused it).
- Gate: numbers on #607; the map's project-management function page shows new processes and people with sources; spend ≤ cap.

### Phase 4 — full run

**4.1 Full window and live proof.** `lead-only`.
- Run the 90-day window. Then ask The Oracle (web) five questions about how project management works and confirm each answer cites message-derived sources.
- Leave `- [ ] live proof` on #607 until the owner has looked at the function page and at the questions the brain would now ask the two managers (generated but **not sent**; the bot stays off per #518).

### Phase 5 — email (blocked)

**5.1 Email collector.** Blocked as in STATUS. When the permission exists: `brain/intake/graph_mail.py`, `GET /users/{id}/messages` with `$select` of sender, recipients, subject, `conversationId`, `receivedDateTime`, `body`, `uniqueBody` (prefer `uniqueBody` — it already excludes quoted history), thread by `conversationId`, then steps 1.4–1.6 unchanged. Tests mirror 1.3.

### 9a. Adversarial cases (all inputs come from outside the repo)

| Input | Hostile case | Test that proves it |
|---|---|---|
| Message text | Text addressed to the model ("ignore your instructions…") | `test_intake_clean.py::test_instruction_text_is_data` — stored verbatim, and `test_relations.py::test_message_instruction_not_followed` (mock asserts prompt wraps passages as quoted data) |
| Renderer output | A rendered thread that the transcript reader mis-parses (timestamps or long names in the speaker label, colons in names) | `test_intake_ingest.py::test_rendered_thread_round_trips_parse_turns` — every message becomes exactly one turn with the right speaker and time |
| Short messages | Hundreds of one-line messages from alternating speakers | `test_intake_ingest.py::test_short_messages_packed_into_full_passages` — passage count is near tokens/400, not near message count |
| Message HTML | Script tags, hidden text, giant inline images | `test_intake_clean.py::test_html_stripped_no_script_no_data_uri` |
| Message text | Pasted password, key or token | `test_intake_clean.py::test_secret_message_dropped_and_blanked` |
| Thread size | One chat with 50,000 messages | `test_intake_gate.py::test_huge_thread_sliced_and_capped` |
| Timestamps | Missing, malformed, far future | `test_intake_ingest.py::test_bad_timestamp_falls_back_to_collected_at_never_future` |
| Encoding | Invalid UTF-8, zero-width and right-to-left control characters | `test_intake_clean.py::test_control_chars_preserved_or_dropped_whole_line` |
| Graph paging | Repeated or looping `nextLink` | `test_intake_graph_chats.py::test_paging_loop_detected` |
| Provider limits | 429 storms, `Retry-After` in the past | `test_intake_graph_chats.py::test_retry_after_bounded`, `test_intake_clickup.py::test_rate_limit_backoff` |
| Duplicates | Same message delivered twice or edited later | `test_intake_ingest.py::test_edit_creates_version_not_duplicate` |
| ClickUp fields | Task or list names containing newlines or `Speaker:` patterns | `test_intake_clickup.py::test_header_fields_escaped_single_line` |
| Deleted content | Message deleted after collection | `test_intake_ingest.py::test_deleted_upstream_marks_item_and_reversions` |
| ScaleDown | Outage or malformed JSON | `test_intake_gate.py::test_outage_leaves_pending` |
| Batch results | Missing, duplicated or foreign passage ids | `test_llm_batch.py::test_result_id_mismatch_rejected` |
| Spend | Runaway loop | `test_intake_ingest.py::test_spend_cap_stops_queueing` |

## 10. Tests required

Every test file named in §9 and §9a, plus: `tests/test_prompts.py` must list any new prompt file; `tests/test_schema.py`, `tests/test_model_seats.py`, `tests/test_dates.py`, `tests/test_relations.py` stay green. Full brain suite command and lint as in `docs/development.md`. No test calls a real provider; live checks are the gates in 2.x, 3.1 and 4.1.

## 11. Constraints, standing rules, gotchas

- Public repo: synthetic fixtures only; counts and scores may be committed, content may not.
- Branch and PR; never push to `main`; the AI merges; reviews are advisory.
- Each write task uses its own worktree. Declare the task class with `ai-task-gates` before editing (code for phases 1–2, production for 3–4).
- `cmap` SQL files are hand-written and idempotent; do not touch generated Drizzle migrations.
- New prompts must be added to `tests/test_prompts.py`.
- New docs need the four-key header (`summary`, `kind`, `status`, `read-when`); run `ai-doc-health --repo . --fix-index` after adding one.
- Times shown to people are in EST. Secrets only in 1Password `vibe_coding`; pass them with `op_run` env references.
- Waiting on CI: `ai-pr-wait` has crashed this harness before; if it does, use `gh pr checks --watch` in the background.
- The interview bot stays off.
- Do not lower `CHATTER_SKIP_SCORE` or the 0.9 drop rule to save money.

## 12. Access and environment

- GitHub: `gh` authenticated as the owner's personal identity.
- 1Password vault `vibe_coding` (titles only): "clickup.com API credentials" (field **api token**; the field named `credential` is empty), "Designflow - Azure Graph client secret (AZURE_CLIENT_SECRET)" (its note holds the app and tenant ids), the ScaleDown and OpenRouter items already used by the brain.
- Brain env on Coolify already has `AZURE_TENANT_ID`, `AZURE_GRAPH_CLIENT_ID`, `AZURE_GRAPH_CLIENT_SECRET` (added 2026-11-16, #593). To add: `CLICKUP_API_TOKEN`, `BRAIN_INTAKE_ENABLED`, `BRAIN_INTAKE_MAX_USD`, and a provider batch key if 2.4 runs.
- Test database and private test store: on edge-dev3, as described in [HANDOFF.d/2026-11-15T1321Z-edge-dev-mimo-oracle-repair-waiting-on-eval-approval.md](HANDOFF.d/2026-11-15T1321Z-edge-dev-mimo-oracle-repair-waiting-on-eval-approval.md).
- Local run: `docs/development.md`.

## 13. Definition of done, risks, open questions

**Done when:** every STATUS row except 5.1 is ✅ with an artifact; code merged with CI green; brain deployed and the deployed commit verified; pilot and full-run numbers on #607; `docs/configuration.md` and `docs/architecture.md` updated; this plan's STATUS current; the handoff deleted under the successor rule; `- [ ] live proof` ticked after the owner's look.

**Risks:**
- *Privacy.* One-to-one chats may hold personal matters. Mitigations: gate label, secret drop, admin-only listing, O4. Rollback: delete sources where `origin IS NOT NULL` and their staging rows (versions make this clean).
- *A cheap model that looks fine on the gold threads but drifts.* Mitigation: quote validation on every relation in production, one retry of failures on the next-cheapest passing candidate (L9), and a re-score of 20 random threads after the full run.
- *Summarize preview unavailable.* Handled in 1.5.
- *Batch latency.* Batches can take up to a day. Acceptable for a backfill; the hourly sweep for new messages may stay synchronous if volume is small — decide from pilot numbers.
- *Graph throttling on large chats.* Bounded backoff; collection is resumable by `(origin, external_id)`.

**Open questions for the owner (business meaning only; also in the handoff §0):**
1. ~~Mailboxes~~ — answered 2026-11-18: yes, both mailboxes. Step 5.1 now waits only on the mailbox permission.
2. ~~One-to-one chats~~ — answered 2026-11-18: private and group chats are both read.
3. ~~Telling the two managers~~ — answered 2026-11-18 (owner: *"Don't announce"*): the system does not announce the reading.

---

## Self-audit (implementation-plan standard)

1. *Could a new session execute this without asking anything?* Yes — §2 and §5 give the system and exact landmarks; §9 names files, behaviour, gates and who does each step; §12 names credentials by location. Gap found and fixed while auditing: the ClickUp vault item's working field name (§12).
2. *Does it carry everything the planning session knew, including what was ruled out?* Yes — §6 (findings and access probes), §7 (eight rejected approaches), §8 (locked vs open), STATUS (owner's words verbatim).
3. *Is the goal clear enough to steer by?* Yes — §1 states the outcome, the order of the two conditions, and that the goal wins over any step.

## Lead launch prompt

```
You are the lead for the project-manager message intake in https://github.com/u2giants/theoracle.
Read AGENTS.md, then plan_pm_message_intake.md (STATUS first, then sections 1, 8, 9), then issue #607.
Start at the first open STATUS row. Create your own worktree and declare the task class with
ai-task-gates before editing.

You do yourself: every step marked lead-only (0.1, 1.1, 1.4, 1.5, 1.6, all of phases 2-4), all
merges, all posts, all live checks, and verification of every helper result against the step's gate.
You hand to your helper, in this order: 1.2 (ClickUp collector), then 1.3 (Teams chat collector).
Your helper is your own tool's smaller model — Haiku (high effort) for Claude Opus, Luna (high)
for Sol, GLM Flash for GLM MAX, Mimo Flash for Mimo Pro. Never a full-strength model.
Rules: https://github.com/popcre/ai-devops/blob/main/templates/system/model-tier-delegation.md

Helper rules: return finished work or an evidenced blocker; no design decisions; no merges or
posts; ask the lead when a step's stop-and-ask trigger fires; taken back after 30 minutes stuck.

Hard rules: no paid model call before the 0.1 forecast is on #607; no message content in the repo,
issues, PRs or logs; cleaning is drop-only; quality gates before cost; the interview bot stays off;
step 5.1 (email) stays blocked until the mailbox permission exists - do not work around it.
Start a fresh session at each marked cut point and re-read the downstream phases first.
```
