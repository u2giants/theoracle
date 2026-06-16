# China Bilingual Implementation Plan (`china_imp.md`)

Status: **Draft / proposal** — not yet implemented.
Owner: Albert (u2giants).
Last updated: 2026-06-16.

## 0. What this is

A plan to serve The Oracle's knowledge to a group of China-based employees in
**Mandarin Chinese**, while keeping **one single company knowledge graph** ("one
brain"). China employees read claims and chat in Chinese; everyone else reads in
English; and a claim created in either language flows to the whole company.

This is a **language** feature, not a **data-residency** feature. All data stays
in the existing US-managed stack (Vercel, Supabase, Trigger.dev). Nothing here
moves data into China or changes hosting.

### In scope

- A bilingual **claim layer**: every approved claim is readable in both English
  and Chinese.
- A bilingual **Brain** (synthesis sections) readable in both languages.
- Chat that **retrieves, answers, and interviews in the reader's language**.
- **Per-locale model routing** (e.g. Chinese extraction via Qwen) using the
  existing `OracleAIClient` route abstraction.
- A **manual** mechanism to put a customer/employee in the "China group" (Albert
  routes them; no auto-detection required).

### Out of scope (explicitly)

- Translating the **UI chrome** (nav, buttons, admin screens). Employees navigate
  in English; only deep business-logic content is localized.
- Translating **evidence quotes**. Per decision below, the verbatim evidence
  quote is always shown in its original (source) language. Only the claim
  *summary* and Brain *narrative* are translated.
- A separate Chinese knowledge segment. There is exactly **one** brain.
- Any data-residency / PIPL / China-hosting work.

## 1. Core design principle

Claims stay **canonical in their source language** and carry **translations as a
sidecar table**, mirroring how `claim_domains`, `claim_metadata`, and
`claim_top_domains` already attach to `claims` (`packages/db/src/schema.ts`).

Two invariants drive every decision:

1. **Evidence is never translated.** `claim_evidence.exactQuote`
   (`packages/db/src/schema.ts`) stays byte-for-byte in the source language,
   because the deterministic quote validator (`quote-validator.ts`,
   strict-for-documents / fuzzy-for-transcripts) matches the stored quote against
   the source text. A translated quote would never match. Translations are
   **display-only renderings**: they never feed quote validation, candidate
   hashing (`candidateHash`), or promotion.

2. **One claim, many renderings; reader sees `COALESCE(my-language, canonical)`.**
   - A claim sourced in Chinese → canonical Chinese summary + an English
     rendering generated for everyone else.
   - A claim sourced in English → canonical English summary + a Chinese rendering
     generated for the China group.
   - At read time, the reader gets the rendering in their language, falling back
     to the canonical summary if no translation exists yet.

This symmetric fallback is what makes "one brain" work in both directions without
forking the graph.

## 2. Plain-English answers to the two open questions

### 2.1 "Chinese FTS" — what it means and what we'll do

**FTS = Full-Text Search.** It's Postgres's built-in keyword search. Today
retrieval blends two signals to rank claims:

1. **Vector search** — semantic similarity using embeddings (meaning-based).
2. **Full-text search** — keyword matching via `to_tsvector('english', summary)`
   in `packages/ai/src/retrieval.ts`.

The problem: Postgres's English text search assumes words are separated by
spaces. **Chinese is written without spaces between words**, so
`to_tsvector('english', ...)` cannot tokenize Chinese text — keyword search would
effectively return nothing for Chinese queries.

**Decision (default):** for Chinese (`zh-CN`) reads, use Postgres's `'simple'`
text-search configuration instead of `'english'`, and rely primarily on the
**vector search** half of the ranking (which is language-agnostic and works well
in Chinese). `'simple'` won't do real Chinese word segmentation, but vector
search carries the quality, and this needs no extra Postgres extensions.

**Optional future upgrade:** install a Chinese word-segmentation extension on
Supabase (`zhparser` or `pg_jieba`) to get true Chinese keyword search. Deferred —
not needed for launch.

### 2.2 "Locale code" — what it means and what we'll do

A **locale code** is a short standard string that identifies a language (and
optionally a region). It's how the system labels "what language is this text /
which language does this reader want."

**Decision (default):**

- `'en'` = English.
- `'zh-CN'` = Simplified Chinese (mainland China).

These two strings are stored in the new `lang` / `source_lang` columns and passed
into retrieval as the reader's locale. Using `zh-CN` (rather than bare `zh`) keeps
the door open for other Chinese variants later (e.g. `zh-TW` Traditional) without
a migration.

## 3. Schema changes (`packages/db/src/schema.ts`)

All schema changes ship through the generated Drizzle migration + `pnpm db:migrate`
**only** — never Supabase MCP `apply_migration` or `drizzle-kit push` (both bypass
the migration journal). See AGENTS.md §6.

### 3.1 Stamp source language on `claims`

```ts
// add to the existing `claims` pgTable
sourceLang: varchar('source_lang', { length: 12 }).notNull().default('en'),
```

`source_lang` records the language the claim was originally created in (the
language of the conversation or document it was extracted from). Existing rows
default to `'en'`.

### 3.2 New sidecar table `claim_translations`

```ts
export const claimTranslations = pgTable(
  'claim_translations',
  {
    claimId: uuid('claim_id').references(() => claims.id).notNull(),
    lang: varchar('lang', { length: 12 }).notNull(),                 // 'zh-CN' | 'en'
    summary: text('summary').notNull(),                              // translated claim text
    embedding: vector('embedding', { dimensions: EMBEDDING_DIM }),   // 1536; same model as claims
    translatedByModelRunId: uuid('translated_by_model_run_id').references(() => modelRuns.id),
    sourceHash: varchar('source_hash', { length: 64 }),              // sha256 of canonical summary at translation time
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.lang] }),
    langIdx: index('claim_translations_lang_idx').on(t.lang),
  }),
);
```

Notes:

- The embedding model `text-embedding-3-small` is **multilingual** and stays at
  `vector(1536)` (locked in `packages/shared/src/domains.ts` via `EMBEDDING_DIM`).
  So the Chinese rendering embeds with the *same* model and dimension — no
  embedding-model change anywhere.
- `sourceHash` lets the translation worker detect when a claim's canonical summary
  has changed and re-translate (and re-embed) just that row.
- `translatedByModelRunId` ties each translation to the model run that produced
  it, consistent with the project's provenance-everywhere approach.

### 3.3 ~~New sidecar table `brain_section_version_translations`~~ — DROPPED

> **Decision (2026-06-16): Brain synthesis is English-only.** Chinese employees
> read **claims** in Chinese but the synthesized **Brain** narrative in English.
> This table and the Brain-translation worker were therefore **not** implemented;
> `getBrainSectionSnippets` returns canonical English markdown only. The original
> design (kept below for reference) would have been:

Brain section versions (`brain_section_versions`) are immutable snapshots, so the
translation is keyed to the **version id** (not the section id).

```ts
export const brainSectionVersionTranslations = pgTable(
  'brain_section_version_translations',
  {
    versionId: uuid('version_id').references(() => brainSectionVersions.id).notNull(),
    lang: varchar('lang', { length: 12 }).notNull(),
    markdown: text('markdown').notNull(),
    structuredContent: jsonb('structured_content'),
    translatedByModelRunId: uuid('translated_by_model_run_id').references(() => modelRuns.id),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.versionId, t.lang] }),
  }),
);
```

### 3.4 What we are NOT adding

- **No** `claim_evidence` translation. Per decision, evidence quotes are shown in
  their canonical/original language only. `claim_evidence.exactQuote` is unchanged.
- **No** change to the candidate → claim pipeline tables. Candidates and evidence
  continue to be created in the source language; quote validation runs
  same-language and is unaffected.

## 4. Retrieval changes (`packages/ai/src/retrieval.ts`)

This is the highest-risk change because of the project's "exactly one retrieval
path, two SQL branches must stay in lockstep" rule (AGENTS.md §"Claim retrieval
has exactly one path").

### 4.1 Thread a `locale` parameter

`searchWithRetrievalPlan()` gains a `locale` argument (`'en' | 'zh-CN'`), supplied
by the caller (the chat route, derived from whether the reader is in the China
group).

### 4.2 Render in the reader's language via COALESCE

In the `pre_filtered` CTE of **both** the hybrid query and the tsvector fallback,
join the translation for the reader's locale and coalesce to canonical:

```sql
FROM claims c
LEFT JOIN claim_translations ct
  ON ct.claim_id = c.id AND ct.lang = ${locale}
LEFT JOIN claim_top_domains ctd ON ctd.claim_id = c.id
LEFT JOIN claim_metadata    cm  ON cm.claim_id  = c.id
WHERE c.status = 'approved'
  AND COALESCE(ct.embedding, c.embedding) IS NOT NULL
  -- existing plan filters unchanged
SELECT DISTINCT
  c.id,
  COALESCE(ct.summary, c.summary)     AS summary,
  COALESCE(ct.embedding, c.embedding) AS embedding,
  c.claim_type, c.impact_score, c.confidence_score
```

Then vector distance and `ts_rank` operate on the **localized** `summary` /
`embedding`. The query embedding already comes from `embedText(userQuery)`
(`packages/ai/src/embeddings.ts`) in the user's own language, so a Chinese query
embedding is compared against Chinese claim embeddings — apples to apples.

Because the pattern is `COALESCE(my-language, canonical)`, it handles **both**
directions automatically:

- English reader, Chinese-sourced claim → sees the `en` rendering.
- Chinese reader, English-sourced claim → sees the `zh-CN` rendering.
- Either reader, claim not yet translated → falls back to the canonical summary.

### 4.3 Chinese full-text search config

For `zh-CN`, swap the FTS configuration from `'english'` to `'simple'` in the
`txt_scored` CTE (see §2.1 for why). Keep `'english'` for `'en'`. The vector half
of the Reciprocal Rank Fusion (RRF) carries Chinese ranking quality.

### 4.4 Keep the two branches in lockstep + extend the parity guard

- Apply the JOIN/COALESCE/FTS change **identically** to the hybrid path and the
  `_searchFallbackTsvector()` path. Divergence here is exactly the silent-bug
  class the existing guard exists to prevent.
- The current parity guard
  (`packages/ai/src/__verify__/retrieval-filter-parity.ts`) only checks that every
  `buildPlanMetadataFilters()` key is interpolated into both branches. It will
  **not** catch a divergent `claim_translations` join. **Extend the guard** to
  also assert the `claim_translations` join + COALESCE appear in both branches.
  The guard runs in CI (`.github/workflows/pr-check.yml`) and via
  `pnpm --filter @oracle/ai verify:retrieval-filter-parity`.

### 4.5 Vector index for the new embedding column

Add an approximate-nearest-neighbour index on `claim_translations.embedding` that
**mirrors** whatever index already exists on `claims.embedding`. Check
`packages/db/migrations/sql/` for the existing ivfflat/hnsw DDL (opclass +
parameters) and copy it for the new column. This is hand-written SQL (see §6).

## 5. Pipeline & worker changes

### 5.1 Stamp `source_lang` at promotion

When a candidate is promoted to a claim, set `claims.source_lang` from the locale
of the originating message/document. Because Albert manually routes employees into
the China group, the originating employee/message carries the locale; the claim
inherits it. Default `'en'` when unknown.

### 5.2 New worker: `claim-translation.ts` (`apps/workers/src/trigger/`)

Triggered when a claim is **approved** or its summary **changes**.

Per run:

1. Determine target languages = all supported langs (`['en', 'zh-CN']`) minus the
   claim's `source_lang`. (Today: exactly one target.)
2. For each target lang missing or stale (`source_hash` ≠ current canonical
   summary hash):
   - Call `OracleAIClient` on a **translation route** (reuse Qwen, or a `general`
     auxiliary model) to translate the canonical `summary` into the target lang.
   - Call `embedText()` on the translated summary.
   - Upsert the `claim_translations` row `(claim_id, lang)` with summary,
     embedding, `source_hash`, and `translated_by_model_run_id`.
3. Idempotent on `(claim_id, lang)`; safe to re-run.

All inference goes through `OracleAIClient` (never a direct provider SDK), per the
project's hard rule.

### 5.3 Synthesis translation

After a `brain_section_version` is created/approved, translate its `markdown`
(and, if used, `structured_content`) into `brain_section_version_translations` for
each non-source language. Same pattern as claim translation.

### 5.4 Chat route (`apps/web/app/api/chat/route.ts`)

- Pass the reader's `locale` into `searchWithRetrievalPlan()`.
- Fetch Brain snippets with the same COALESCE-by-locale rendering (translation if
  present, else canonical).
- Instruct the model (in the system / interview prompt) to **answer in the
  reader's language**. This is where the per-locale interview model selection
  (Claude vs Qwen) takes effect.

### 5.5 Admin display (optional, low priority)

In the admin claims views (`apps/web/app/admin/...`), show canonical summary +
each translation side by side so reviewers can spot a bad translation. Evidence
quotes remain shown in their original language only.

## 6. Migration mechanics

1. Edit `packages/db/src/schema.ts` (§3) → generate the Drizzle migration
   (`packages/db/migrations/0*.sql`). Do not hand-edit generated files.
2. Add hand-written SQL in `packages/db/migrations/sql/` for:
   - the ANN vector index on `claim_translations.embedding` (mirror
     `claims.embedding`'s index), and
   - any FTS-related config helpers if needed.
3. Ship via `pnpm db:migrate`. Run `pnpm db:check-drift` if unsure of state.
4. Never use Supabase MCP `apply_migration` for generated Drizzle migrations.

## 7. Backfill

A one-off script enqueues translation work for existing content:

- For every existing **approved claim** (all currently `source_lang = 'en'`),
  enqueue `claim-translation` to generate the `zh-CN` rendering + embedding.
- For every current **brain section version**, enqueue synthesis translation to
  `zh-CN`.

This is the bulk of the one-time LLM/translation cost. Run it as a queued/batched
job, not interactively. Consider the provider Batch API path
(`provider_batch_jobs`) for the 50% discount if the translation route's provider
supports batch.

## 8. Model routing (per-locale)

Everything routes through `OracleAIClient`, so per-locale model choice is config,
not new architecture. Recommended starting routes for the China locale:

- **Extraction (zh):** Qwen-Max tier. A Chinese-native model is less likely to
  normalize/paraphrase Chinese source text, which protects strict verbatim quote
  matching. Verify structured-output (JSON) reliability against the extraction
  schema in a wet test before trusting at volume; Gemini Flash remains a strong
  multilingual fallback.
- **Interview (zh):** default to **Claude** (Haiku 4.5 / Sonnet 4.6) for
  conversational steerability and faithful adherence to the interview system
  prompt, with **Qwen-Max** as an A/B challenger (strong native Mandarin register,
  single-vendor with extraction). Do **not** default DeepSeek for interviewing.
- **Translation route:** reuse Qwen or a `general` auxiliary model.

Confirm the exact Qwen model id resolves in the catalog
(`packages/ai/src/model-capabilities/sources/qwen.ts`) — a wrong id 404s the
route.

## 9. Testing & verification

- **Migration:** apply on a branch DB; confirm new tables/columns and indexes
  exist; `pnpm db:check-drift` clean.
- **Retrieval parity:** extend and run
  `pnpm --filter @oracle/ai verify:retrieval-filter-parity`; confirm the
  `claim_translations` join is asserted in both branches.
- **Retrieval behavior:** with a seeded bilingual claim, confirm:
  - `locale='zh-CN'` returns the Chinese rendering; `locale='en'` returns English.
  - A claim with no translation falls back to canonical in both locales.
  - Chinese query embeds and retrieves the Chinese rendering (vector half).
- **Provenance:** confirm quote validation still passes for same-language evidence
  and that translations never touch the candidate/promotion path.
- **End-to-end:** China-group user chats in Chinese → gets a Chinese answer backed
  by claims surfaced in Chinese, with the original-language evidence quote.

## 10. Rollout phases

1. **Schema + backfill plumbing** — add tables/columns, translation worker,
   synthesis translation, vector index. No user-visible change yet.
2. **Backfill** — translate existing approved claims + brain versions to `zh-CN`.
3. **Retrieval locale** — land the COALESCE/FTS change + parity-guard extension
   behind the `locale` parameter (defaults to `'en'`, so no behavior change for
   existing users).
4. **China group go-live** — route the China employees' locale to `'zh-CN'`, point
   their extraction/interview routes at the chosen models, and turn on
   Chinese-language chat.

## 11. Risks & watch-items

- **Lockstep SQL divergence** between the hybrid and fallback retrieval branches —
  mitigated by extending the parity guard (§4.4).
- **Chinese keyword search is weak** under `'simple'` config — accepted for
  launch; vector search carries it; `zhparser` is the future upgrade (§2.1).
- **Translation quality / drift** — `source_hash` triggers re-translation when a
  canonical summary changes; admin side-by-side view (optional) helps catch bad
  translations.
- **Backfill cost** — one-time, batched; use Batch API discount if available.
- **Provenance regressions** — guard the invariant that translations are
  display-only and never enter validation/hashing/promotion.

## 12. Open decisions (resolved defaults)

| Question | Decision |
|---|---|
| Translate evidence quotes? | **No** — canonical/original-language quote only. |
| Chinese full-text search strategy | **`'simple'` config now**, vector-dominant; `zhparser` later (optional). |
| Locale codes | **`'en'` and `'zh-CN'`**; `lang`/`source_lang` stored as `varchar(12)`. |
| Locale assignment | **Manual** — Albert routes employees into the China group (set `employees.locale = 'zh-CN'`). |
| Separate Chinese knowledge segment? | **No** — one brain, bilingual claim rendering. |
| Translate the synthesized Brain? | **No** — Brain synthesis is English-only; only **claims** are bilingual. |

## 13. File-by-file touch list

- `packages/db/src/schema.ts` — `claims.source_lang`, `claim_translations`,
  `brain_section_version_translations`.
- `packages/db/migrations/0*.sql` — generated DDL (Drizzle).
- `packages/db/migrations/sql/*.sql` — ANN index on `claim_translations.embedding`.
- `packages/ai/src/retrieval.ts` — `locale` param, COALESCE rendering, FTS config,
  applied to both branches.
- `packages/ai/src/__verify__/retrieval-filter-parity.ts` — extend guard for the
  translation join.
- `apps/workers/src/trigger/claim-translation.ts` — new translation worker.
- `apps/workers/src/trigger/` (synthesis path) — brain version translation.
- `apps/web/app/api/chat/route.ts` — pass locale; localize Brain snippets;
  answer-in-reader-language prompt.
- `apps/web/app/admin/...` — optional side-by-side translation review.
- Promotion path (engines/worker) — stamp `claims.source_lang`.
- `docs/architecture.md`, `DECISIONS.md` — record the bilingual-claim decision.
