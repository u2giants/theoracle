# Fix Plan: Message-extraction batch boundary splits conversations

Status: **IMPLEMENTED IN SOURCE 2026-06-26.** Sync and batch extraction now use `selectPendingConversations()` in `apps/workers/src/trigger/claim-extraction.ts`; carry-in context is formatted by `formatConversationSegment(..., { carryIn })`; settings are `extraction_char_budget` and `extraction_carry_in_count`. Deploy workers and apply `78_fail_loud_model_routing_settings.sql` before treating production as fixed. Original brief retained below for context.

---

## 0. What this project is (orientation)

The Oracle is an evidence-backed enterprise knowledge graph. Background workers read employee **messages** (chat + ingested Teams meeting transcripts) and extract operational **claims**, each backed by a verbatim **quote** from a specific message. Deterministic validators then promote claims. **Read `AGENTS.md` first.** Key facts for THIS task:

- Monorepo (`pnpm`+`turbo`): `apps/workers` holds the Trigger.dev background tasks; `packages/ai` holds the AI client + prompts; `packages/oracle-engines` holds the deterministic extraction/promotion/validation.
- Messages live in the `messages` table with an `extraction_status` column (`pending` → processed). A worker pulls `pending` user messages, groups them into conversation **segments**, sends each segment to the extraction model, validates the returned claims (each claim's `exactQuote` MUST be a verbatim substring of one real message), and promotes the survivors.
- There are **two extraction dispatch modes** (toggled by `settings.extraction_dispatch_mode`): synchronous (`claim-extraction.ts`) and batch (`claim-extraction-batch-submit.ts` + `claim-extraction-batch-drain.ts`, ~50% cheaper via provider Batch APIs). **Both have the bug below.**

## 1. The problem (what to fix and why it matters)

Context is everything in a conversation. Three people can debate a point back-and-forth for ten minutes; no single message states the operational rule — the *thread* does. If you cut that thread in the middle, the model never sees the connected context and either misses the rule or extracts a distorted one.

The current code cuts threads at an **arbitrary fixed-count boundary, not a semantic one**:

In `apps/workers/src/trigger/claim-extraction.ts` (and identically in `claim-extraction-batch-submit.ts`):

```ts
export const BATCH_SIZE = 100;
export const SEGMENT_GAP_MS = 60 * 60 * 1000; // 60 min

const pendingMessages = await db
  .select({ ... })
  .from(messages)
  .where(and(eq(messages.extractionStatus, 'pending'), eq(messages.role, 'user')))
  .orderBy(messages.createdAt)
  .limit(BATCH_SIZE);             // <-- (1) GLOBAL limit of 100, across ALL channels

const segments = groupIntoSegments(pendingMessages); // <-- (2) groups the already-truncated subset by channel + 60-min gap
```

The `LIMIT(BATCH_SIZE)` happens **before** `groupIntoSegments` (`claim-extraction.ts` ~line 1008). So:

- A long same-channel discussion can be **split at message #100**, mid-argument, regardless of the 60-minute gap logic — because the 101st message of that conversation simply isn't in this batch. It's picked up on the *next* cron tick as a *separate* segment with no connection to the first half.
- The 100 messages are pulled **globally across all channels** ordered by time, so a single batch can be a fragment of several unrelated conversations, and a busy channel can be arbitrarily sliced.

This is the **same class of bug** as the flowchart-image incident (where a connected diagram was chunked into independent windows so the model never saw the whole flow). It's documented in `HANDOFF.md`. It was deliberately NOT fixed in the 2026-06 session because it's a real design change, not a one-liner.

## 2. Where the code lives (exact map)

| Thing | File / symbol |
|---|---|
| Sync extraction worker | `apps/workers/src/trigger/claim-extraction.ts` — `BATCH_SIZE`, `SEGMENT_GAP_MS`, the `pendingMessages` select (~line 195), `groupIntoSegments()` (~line 1008), `processSegment()` (~line 309), `formatConversationSegment()` |
| Batch-mode submit worker | `apps/workers/src/trigger/claim-extraction-batch-submit.ts` — same select + grouping pattern (~line 146) |
| Batch-mode drain worker | `apps/workers/src/trigger/claim-extraction-batch-drain.ts` — polls provider batches, runs `processSegmentOutput` |
| Extraction prompt | `packages/ai/src/prompts/` (`EXTRACTION_SYSTEM_PROMPT`, `EXTRACTION_PROMPT_VERSION`), `ExtractionOutputSchema` |
| Quote validation (the hard constraint) | `packages/oracle-engines/src/extraction/quote-validator.ts` — a claim's `exactQuote` must be a verbatim substring of the message it cites |
| Message schema | `packages/db/src/schema.ts` — `messages` (`extraction_status`, `channel_id`, `created_at`, `content`, `role`) |

**Analogous fix already shipped (use it as the template):** the document-ingestion path was fixed in this session with **structure-aware chunking + wide windows**. See `apps/workers/src/trigger/document-ingestion.ts` (`chunkTextStructured`, `MAX_DOCUMENT_TEXT_CHARS`, `MAX_IMAGE_TEXT_CHARS`, `buildDocumentChunkWindows`). The conceptual lesson — "never cut a connected unit of meaning at an arbitrary boundary; size the window to hold the whole unit" — is exactly what the message path needs.

## 3. The fix — design

**Goal:** a conversation (a same-channel run of messages with no long gap) is never split across extraction batches. The model always sees the whole connected thread, plus enough prior context to interpret it.

### Step 1 — Select by conversation, not by a global count
Replace "global `LIMIT(100)` then group" with "pick whole conversations up to a budget":
- Query the set of channels that have any `pending` user messages.
- For each channel (oldest-pending first, fairness-bounded), pull the **entire** contiguous pending run for that channel, then segment it by `SEGMENT_GAP_MS` into conversations. A conversation is the atomic unit — never split it across batches.
- Accumulate whole conversations into the batch until a **token/char budget** is reached (NOT a message count). Mirror the document path's `MAX_DOCUMENT_TEXT_CHARS`-style budget so a single model call holds a whole conversation. If ONE conversation exceeds the budget, that's the genuine large-input case — handle explicitly (Step 3), don't silently truncate.
- Keep `BATCH_SIZE` only as a coarse safety cap on total messages per cron tick, applied at the **conversation boundary** (stop adding whole conversations once near the cap), never mid-conversation.

### Step 2 — Carry-in context (so a continued conversation still has its history)
A conversation can legitimately span cron ticks if it's still ongoing (new messages arrive between ticks). For each segment, prepend the **prior N messages** of the same channel (already-extracted ones) as **read-only context** the model may use to interpret the segment but must NOT quote.
- Add these as a clearly-labeled context block in the prompt ("CONTEXT — earlier in this conversation, for interpretation only; do not extract claims from or quote these lines").
- **Critical provenance constraint:** the quote-validator requires every `exactQuote` to be a verbatim substring of a message *in the segment being processed*. If the model quotes a carry-in context message that isn't a segment member, validation will (correctly) reject it. So either (a) keep carry-in strictly non-quotable and prompt accordingly, or (b) include carry-in message ids in the validatable set. Decide and document; (a) is safer and matches the "context, not evidence" intent.

### Step 3 — Handle a conversation larger than the model window
A genuinely huge single conversation can exceed the extraction model's context. Options (pick + document in `DECISIONS.md`):
- Sliding window WITH overlap + carry-in summary, so adjacent windows share boundary context (like document chunking overlap, but semantic). Ensure each claim still quotes a message present in its window.
- Or a two-pass: summarize the conversation, then extract against the full text in a large-context model. Heavier.
Whatever you choose, **log loudly** when a conversation is too big to fit (do not silently truncate — that's the anti-pattern this whole effort is about).

### Step 4 — Apply to BOTH dispatch modes
The sync (`claim-extraction.ts`) and batch (`claim-extraction-batch-submit.ts`) workers share the select+group pattern. Factor the new "select whole conversations within a budget + build carry-in" logic into a shared helper (e.g. in `claim-extraction.ts` exporting it, or a new module) and use it in both, so they can't drift.

## 4. Step-by-step implementation

1. Write `selectPendingConversations(db, { charBudget, maxMessages, carryInCount })` returning `Array<{ channelId, segment: FormattedMessage[], carryIn: FormattedMessage[] }>`. It pulls whole channel runs, segments by `SEGMENT_GAP_MS`, packs whole conversations to `charBudget`, and fetches carry-in (prior already-extracted messages) per segment.
2. Replace the `LIMIT(BATCH_SIZE)` select + `groupIntoSegments` calls in BOTH `claim-extraction.ts` (~195/~1008) and `claim-extraction-batch-submit.ts` (~146) with the new helper.
3. Update `formatConversationSegment` / the prompt assembly to include a labeled non-quotable carry-in block. Bump `EXTRACTION_PROMPT_VERSION`.
4. Keep `extraction_status` lifecycle correct: only the SEGMENT messages flip `pending → processing → processed`; carry-in messages are already `processed` and must NOT be re-flipped or re-extracted (idempotency).
5. Implement Step 3 (oversized conversation) with loud logging + a chosen strategy.
6. Add a settings knob (e.g. `extraction_char_budget`, `extraction_carry_in_count`) so it's tunable without redeploy; document in `docs/configuration.md`.
7. Update `HANDOFF.md` (remove this from the open list once done) and `docs/architecture.md` (the message-extraction section).

## 5. Edge cases / gotchas

- **Quote provenance is sacred.** Every promoted claim must quote a real message in its segment. Carry-in context must not be quotable, or you'll get false validation failures (or, worse, claims whose evidence message isn't linked). This is the single biggest correctness trap.
- **Idempotency.** The worker can run again before the previous finished; messages are claimed by flipping to `processing`. Make sure conversation selection + carry-in never double-process or skip. Re-running must be safe.
- **Fairness / starvation.** Don't let one very busy channel monopolize every tick and starve others. Bound per-tick work across channels while still never splitting a single conversation.
- **Batch mode SLA.** Provider Batch APIs have a 24h SLA; the drain task (`claim-extraction-batch-drain.ts`) runs unconditionally to drain in-flight batches even after the mode flag flips. Don't break that — see `AGENTS.md` §10 "Two-phase batch worker".
- **`SEGMENT_GAP_MS`** (60 min) is the conversation boundary heuristic. Consider whether speaker-change or topic-shift signals should refine it — but a time gap is a reasonable v1; don't over-engineer.
- **Trigger schedule slots are 10/10** — do not add a new `schedules.task()`. Reuse the existing extraction schedule.
- The document path's fix is the proven template; mirror its "budget-sized window, never cut mid-unit" approach.

## 6. Testing / acceptance

- Unit-test `selectPendingConversations`: a 250-message single-channel conversation must come out as whole conversation(s) packed to budget, **never** split at message 100; two interleaved channels must not bleed into each other's segments.
- Test carry-in: a segment that continues a prior conversation includes prior messages as context, and a claim that tries to quote a carry-in (non-segment) message is rejected by the quote-validator (proving provenance holds).
- Engine smokes still green: `corepack pnpm --filter @oracle/engines verify:r5 verify:r7` and `--filter @oracle/workers typecheck`.
- Manual: seed a long back-and-forth in one channel that crosses the old 100-msg boundary; run extraction; confirm the operational rule that depends on the *whole* thread is extracted as one coherent claim, not split/missed.

**Acceptance criteria:** no conversation is ever split across extraction batches; each segment carries enough prior context to be interpretable; provenance (quote-validation) still holds; both sync and batch modes use the same selection logic; oversized conversations are handled explicitly and logged, never silently truncated.

## 7. Logistics for a fresh dev

- Deploy workers: `corepack pnpm --filter @oracle/workers run deploy` (or Trigger MCP `deploy`).
- Toggle dispatch mode for testing via `settings.extraction_dispatch_mode` (`'sync'` | `'batch'`) — read every cron tick, no redeploy.
- Prod DB reads: use the **session pooler** string from 1Password (`Supabase DB Direct URL - The Oracle (CURRENT PROD …)` → `oracle_session_pooler`); the direct host is IPv6-only. `.env.local` may point at the old project. See `AGENTS.md` §10.
- The related, already-fixed document path (`document-ingestion.ts`, `chunkTextStructured`) is your reference implementation for "don't cut connected meaning."
