# SECURITY NOTE

The Vercel token shared during overnight setup is in the chat transcript. **Rotate it at https://vercel.com/account/tokens before sharing this repo widely.** Also rotate any Supabase service-role / DB URL / Trigger.dev / OpenRouter keys that were pulled into `.env.local` during bootstrap (they remain only in the local untracked `.env.local`, but the token used to fetch them was in chat).

---

# Decisions log

This file is the running log of every assumption, stub, and resolution made by the overnight build agent. Each entry cites the spec section it conforms to (or notes "spec underspecified") and the safer alternative that was ruled out.

---

## Phase 0 — Bootstrap

### D0.1 — Repo bootstrap

- **Decision**: `git init`, set `git@github.com:u2giants/theoracle.git` as `origin`, commit directly to `main`.
- **Spec**: Per user decision #4 (commit per phase to main).
- **Alternative ruled out**: PR workflow — user explicitly authorized direct commits to `main` overnight.

### D0.2 — Toolchain

- **Decision**: pnpm + Turborepo. Node 24 + npm 11 already installed. Install pnpm globally.
- **Spec**: Part 2.1 (TypeScript only), Part 11 Phase 1 task 1 ("Initialize Turborepo / Next.js App Router").

### D0.3 — Vercel env pull

- **Decision**: Pull dev-environment env vars from Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` into untracked `.env.local`. Confirmed `.gitignore` blocks all `.env*` except `.env.example` before any pull happens.
- **Spec**: Part 3.4 (connection rules — env vars must not reach browser).

### D0.4 — BLOCKER: Vercel env vars present but EMPTY

- **Found**: All eight required env vars (`DATABASE_URL`, `DIRECT_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `TRIGGER_SECRET_KEY`) exist on the Vercel project under Production and Preview environments, marked "Encrypted" in `vercel env ls` — but when pulled they decrypt to empty strings (`""`). The variables were created but their values were never assigned.
- **Impact**: Database migrations cannot be run live. The acceptance gate "admin authenticates via magic link" cannot be wet-tested. Trigger.dev workers, OpenRouter chat, and pgvector retrieval cannot be exercised end-to-end.
- **Strategy (per user decision #5)**: Stub with safest minimal default and keep moving. The code builds correctly and is wired to use these vars when populated. A `.env.example` documents the full required surface. All Phase 1–3 code is written so that running migrations and tests becomes a one-step user action once secrets are populated.
- **User action required in the morning**:
  1. Populate the eight env vars on Vercel (https://vercel.com/popcre/theoracle/settings/environment-variables) with real Supabase / OpenRouter / Trigger.dev values for all three environments (Production, Preview, **and Development**).
  2. Re-run `npx vercel@latest env pull .env.local --environment=development --token <NEW_TOKEN> --yes` (rotate the token first).
  3. Run `pnpm db:migrate` from the repo root to push the schema + RLS + seed to Supabase.
  4. Optionally set `OPENAI_API_KEY` if real embeddings are wanted (see D3.x for the embedding stub fallback).
- **Spec**: Part 3 (managed cloud architecture). The blocker is environmental, not architectural.

### D0.5 — Existing remote content

- **Found**: `origin/main` already contained `oracle_master_spec.md` (commit 7997486). Pulled and kept that file as the canonical spec; new code lands on top.

### D0.6 — BLOCKER: cannot install dependencies locally (no symlink permission)

- **Found**: The Windows account running this build (`ahazan2`) does not have the `SeCreateSymbolicLinkPrivilege`. Confirmed by a direct `New-Item -ItemType SymbolicLink` test returning "Administrator privilege required for this operation."
- **Impact**: Both `pnpm install` and `npm install -w` fail at the workspace symlink step, regardless of pnpm/npm version (tried pnpm 8.15.9, 9.5.0, 9.15.4, 10.0.0, npm 11.9.0). pnpm leaves `_tmp_<PID>` package extraction directories that it cannot rename to the final name, and the workspace linking step fails with `EISDIR: illegal operation on a directory, symlink ...`.
- **Result**: `pnpm typecheck`, `pnpm lint`, `pnpm build`, `pnpm db:migrate` could not be wet-tested locally. All source code is written to the spec, but the acceptance gates "schema deploys", "admin authenticates", and "RLS blocks cross-channel reads" require the user to either (a) enable Windows Developer Mode (Settings → For Developers → Developer Mode ON), or (b) run on a different machine, or (c) push and let Vercel build it.
- **Strategy (per user decision #5)**: Documented blocker, code is committed and pushed. CI / Vercel will install cleanly because they run with symlink permission. `pnpm-lock.yaml` is committed once the user runs install in a working environment.
- **User action required**:
  1. Enable Developer Mode on Windows (Settings → System → For Developers → Developer Mode = On). This grants symlink rights without an admin shell.
  2. Run `pnpm install` from the repo root.
  3. Populate the eight empty Vercel env vars (see D0.4) and `npx vercel@latest env pull .env.local --environment=development ...` again.
  4. Run `pnpm db:migrate` to push the schema and seed.
  5. Run `pnpm typecheck && pnpm build` to verify nothing regressed.

## Phase 1 — Foundation

### D1.workspace — pnpm + Turborepo

- **Decision**: pnpm workspaces (`pnpm-workspace.yaml`) + Turborepo 2.3.3 (pinned, not caret — see D1.turbo-pin). Strict TypeScript per `tsconfig.base.json`. `apps/web` is the only app for Phases 1-3; `apps/workers` (Trigger.dev) is scaffolded in Phase 4 stub.
- **Spec**: Spec Part 2.1 (TypeScript only), Part 3 (managed cloud).

### ~~D1.turbo-pin~~ — Turbo pinned to 2.3.3 (RESOLVED 2026-05-20)

- **Original decision**: Pinned turbo to exactly `2.3.3`. Newer versions allegedly failed Windows install.
- **Resolution**: Root cause was exFAT (D0.6), not turbo. Once the repo moved to NTFS, turbo 2.9.x installs cleanly. Now on `^2.9.14`.

### ~~D1.next-version~~ — Next 15.1.4 (RESOLVED)

- **Resolution**: Bumped past the CVE to Next 16.2.6. See HANDOFF.md commit log.

### D1.embedding-dim — vector(1536) locked

- **Decision**: `EMBEDDING_DIM = 1536` in `@oracle/shared`. OpenRouter doesn't host `text-embedding-3-small` directly. Phase 3 embeddings call OpenAI's REST endpoint when `OPENAI_API_KEY` is present and return a deterministic-zero vector (length 1536) when not.
- **Spec**: Part 6 schema uses `vector(1536)` — locked dimension.
- **Safer alternative ruled out**: Silently switching to a 768-dim model (e.g. Cohere via OpenRouter). Would require a schema migration and break the spec's traceability assumption.

### D1.auth-provider-stub — magic_link_dev provider

- **Decision**: Added `magic_link_dev` to the `auth_provider` Postgres enum (spec lists three production providers; this extends it for Phase 1 dev only). The first-login linker (`packages/auth/src/link.ts`) implements the spec 4.4 contract exactly; only the upstream provider differs.
- **Spec**: Part 4.5 (provider notes — extension allowed since allowlist still gates access).
- **Action item**: In production, wire Supabase Auth's Microsoft / Google / Authentik providers and stop allowing the `magic_link_dev` row. A migration can drop it once unused: `DELETE FROM employees WHERE auth_provider = 'magic_link_dev'` is NOT correct (it would delete real rows that linked through the dev path); instead update those rows' `auth_provider` to the real provider on next login.

### D1.test-employee — temporary second seed row

- **Decision**: Seed inserts a SECOND row `test-employee@oracle.local / Test Employee` so Phase 2's "two employees can chat" acceptance gate can be exercised once secrets are populated. Marked `is_admin = false`.
- **Action item**: Delete this row before production: `DELETE FROM employees WHERE email = 'test-employee@oracle.local'`.
- **Safer alternative ruled out**: Seeding 18 employees — they don't exist yet in the spec, and inventing names would create stale data. One synthetic test row is the minimum that demonstrates RLS works.

### D1.storage-bucket — TODO for company_documents

- **Decision**: Phase 2 needs the `company_documents` Supabase Storage bucket. Cannot create it via SQL migration (Supabase Storage buckets are managed via the Storage API or dashboard). Adding a TODO instead of stubbing in code.
- **Action item**: In the Supabase dashboard for the linked project, go to Storage → New bucket → name `company_documents`, set to private, then run the Storage RLS policy that only allows authenticated employees to read their own uploads and channel-attachment documents (use spec 7.2 documents policy as the template).

### D1.rls-policies — admin reads via service role, not RLS bypass

- **Decision**: Admin reads on intelligence tables (claims/gaps/etc.) and admin views go through the SERVICE_ROLE Drizzle client (`getDirectDb`) in privileged server routes, NOT through `current_employee_is_admin()` USING clauses with the authenticated role.
- **Spec**: Part 7.3 "Default recommendation: access admin views only through privileged server routes."
- **Implementation note**: The RLS policies in `21_rls_policies.sql` still grant admins access for direct-from-authenticated-client reads if we ever expose that route, but the `/admin/*` routes in `apps/web` always go through `getDirectDb()` (service role) for clarity.



## Phase 2 follow-ups — addressed late

### D2.multi-identity — one employee, many auth identities

- **Decision**: Split `(auth_provider, auth_user_id, auth_provider_subject)` off the `employees` table into a new `employee_identities` table. One employee can hold multiple identities (Google, Microsoft 365, future Authentik). The linker resolves a session by `(auth_provider, auth_user_id)` first; on miss, falls back to matching the verified provider email against `employees.email` to bootstrap a new identity row.
- **Why**: Originally `employees` had `auth_user_id UNIQUE` and `auth_provider` as single columns, so each (real human, provider) combo needed its own employees row. When Albert signed in with Microsoft after first signing in with Google, the M365 login created a SECOND employees row, breaking the "one human = one employee" invariant the rest of the system depends on (channel participants, claim attribution, gap targeting all key off employee_id).
- **Spec**: Part 4 doesnt explicitly call for multi-identity but doesnt preclude it; "Every human user must map to exactly one row in employees" is preserved — identities sit beside, not inside.
- **Schema migration**:
    - `15_employee_identities.sql` — creates the table (DDL only).
    - `20_rls_helpers.sql` — `current_employee_id()` now joins through `employee_identities`.
    - `21_rls_policies.sql` — adds RLS policies for the new table; rewrites `employees_self_select` to use the helper instead of querying `auth_user_id` directly.
    - `40_employee_identities_data.sql` — idempotent: copies any pre-existing `employees.auth_*` values into identity rows, performs the one-shot Albert merge (re-points the popcre identity onto the gmail employee, deletes the popcre employee row), then NULLs the deprecated columns so stale reads can't silently use them.
- **Deprecated columns kept**: `employees.auth_user_id`, `employees.auth_provider`, `employees.auth_provider_subject` remain on the table (nullable, NULL-filled by 40_*.sql) to avoid a forced Drizzle column-drop migration in the middle of an active session. A follow-up commit will fully remove them after the team confirms no consumer still reads them.
- **Safer alternative ruled out**: Adding a `secondary_emails` array column on `employees`. Loses the per-identity audit trail (`linked_at`, per-identity `last_login_at`, per-provider `auth_provider_subject`) and conflates "alias email" with "second authentication path".
- **Action item**: After Phase 6, drop the deprecated columns from `employees` in a clean migration. Add an admin UI to manually link/unlink identities (e.g. when an employee gets a new Microsoft account).

## Phase 3.5 — dependency modernization (2026-05-20)

### D3.5.bump-everything-mature — bump now while the surface is small

- **Decision**: Bumped every dependency that's mature and not blocked by ecosystem support. Skipped only `typescript` 5→6 and `eslint` 9→10 because those were released within weeks and downstream tools haven't confirmed support yet.
- **Why**: We're ~20% into the build. Doing these migrations now touches ~6 files; doing them later would touch dozens. The codebase being small is the cheapest possible time to absorb breaking changes.
- **Bumps applied**:
    - `react`, `react-dom` 19.0.0 → ^19.2.6 (minor within React 19)
    - `@types/react`, `@types/react-dom` → ^19.2.x
    - `@types/node` 22 → ^24.12.4 (matches Node 24 LTS runtime)
    - `turbo` 2.3.3 → ^2.9.14 (D1.turbo-pin reason was actually exFAT/D0.6)
    - `dotenv` 16 → ^17.4.2 (only dropped Node 12)
    - `eslint-config-next` 15.1.4 → ^16.2.6 (match Next 16; eslint 9 stays — peers say >=9)
    - `lucide-react` 0.469 → ^1.16.0 (v1 stable cut; Send/Users/Paperclip imports still work)
    - `drizzle-kit` 0.30.6 → ^0.31.10
    - `drizzle-orm` 0.38.3 → ^0.45.2 (back-compat schema/query API)
    - `@trigger.dev/sdk` + `@trigger.dev/build` 3 → ^4.4.6 — **no code change**: trigger.dev v4 keeps the `@trigger.dev/sdk/v3` subpath export. Also drops `uuid@9`.
    - `@supabase/ssr` 0.5 → ^0.10.3 — migrated to `getAll`/`setAll` cookie adapter shape; consolidated callback/signout routes onto the shared `getServerSupabase()` helper.
    - `ai` 4 → ^6.0.187 — `tool({ parameters })` → `tool({ inputSchema })`, `maxSteps: 4` → `stopWhen: stepCountIs(4)`, `usage.promptTokens/completionTokens` → `usage.inputTokens/outputTokens`.
    - `@openrouter/ai-sdk-provider` 0.7 → ^2.9.0 (paired with AI SDK v6).
    - `zod` 3 → ^4.4.3 — only one usage shift visible (`z.string().uuid()` → `z.uuid()` in chat route body schema).
    - `tailwindcss` 3 → ^4.3.0 — `tailwind.config.ts` deleted (v4 is CSS-based), `postcss.config.js` switched to `@tailwindcss/postcss`, `globals.css` rewritten with `@import "tailwindcss"`, `@custom-variant dark`, and `@theme inline` color token mapping. Token bridge: `--color-X: hsl(var(--X))` so all existing `bg-primary`/`text-foreground`/etc. classes resolve unchanged.
    - `tailwind-merge` 2 → ^3.6.0 (Tailwind 4 alignment).
    - `tailwindcss-animate` (deprecated for v4) → replaced with `tw-animate-css` ^1.4.0 (`@import "tw-animate-css"` in globals.css).
    - `typescript` ^5.7.3 → ^5.9.3 across all workspaces (within v5).
- **Bumps deferred**:
    - `typescript` 5 → 6 — released weeks ago; Drizzle/Next/AI SDK haven't all confirmed support
    - `eslint` 9 → 10 — `eslint-config-next@16` peers say `>=9.0.0` but doesn't claim v10
- **Verification**: `pnpm typecheck` green across all 7 workspaces. `pnpm --filter @oracle/web build` green with placeholder env. All routes correctly dynamic.
- **Deprecation outcome** — **correction to earlier overclaim**:
    - `uuid@9` is truly gone (trigger.dev v4 dropped it for `ulid`). Lockfile has 0 references.
    - `@esbuild-kit/core-utils` + `@esbuild-kit/esm-loader` are **still present**. `drizzle-kit@0.31.10` still lists `@esbuild-kit/esm-loader` as a direct dep alongside `tsx`. The install-time warning line stays quiet on subsequent installs because pnpm only emits it when packages are *added*, not on every install. Per our agreement, we are **not** forcing it away with `pnpm.overrides` — that would risk breaking drizzle-kit's CLI bootstrap. We'll absorb the upstream fix when drizzle-kit fully migrates off esbuild-kit.
- **Files touched**: every `package.json`; `apps/web/postcss.config.js`; `apps/web/app/globals.css`; deleted `apps/web/tailwind.config.ts`; `apps/web/lib/supabase/server.ts`; `packages/auth/src/server.ts`; `apps/web/app/auth/callback/route.ts`; `apps/web/app/auth/signout/route.ts`; `apps/web/app/api/chat/route.ts`.

## Phase 3 post-deployment fixes (2026-05-21)

### D3.oracle-vision-fix — skip Storage downloads for text-only models

- **Decision**: In `apps/web/app/api/chat/route.ts`, detect whether the configured model is vision-capable **before** querying `message_attachments`. If the model is text-only, skip the Supabase Storage download entirely.
- **Why**: The original code downloaded all attachments first, then conditionally stripped non-text parts. On text-only models (e.g. DeepSeek), the Storage download added latency and occasionally timed out on the second+ message in a channel, causing silent Oracle failures.
- **Pattern**: `visionCapable = /claude|gpt-4o|gemini|llava|pixtral|qwen.*vl|minicpm/i.test(modelName)` — conservative allowlist rather than denylist, so new models default to text-only until confirmed vision-capable.

### D3.oracle-upload-trigger — Oracle fires after document uploads

- **Decision**: After a successful document upload (`DocumentUpload.onDone`), the client calls `fetchOracleReply`. In DMs this always fires; in group chats only when the upload caption starts with `@oracle`.
- **Why**: The original upload flow inserted the attachment into the DB but never called `POST /api/chat`. Oracle was silent after every document upload.

### D3.oracle-error-surfacing — show Oracle errors in the chat UI

- **Decision**: Added `oracleError` state to `channel-chat.tsx`. When `POST /api/chat` fails (non-2xx or thrown), an error bubble appears inline in the message list instead of silently failing.
- **Why**: Failures were invisible to the user (only logged to console). With multiple failure modes (model timeouts, API key errors, Storage timeouts), surfacing the error is essential for diagnosing and retrying.

### D3.oracle-race-lock — `oracleFetchingRef` prevents double-fire

- **Decision**: A `useRef<boolean>` lock in `channel-chat.tsx` prevents concurrent `fetchOracleReply` calls. If a call is already in flight, subsequent triggers are dropped with a console log.
- **Why**: `DocumentUpload.onDone` and `sendMessage` can both fire Oracle within milliseconds when a message is sent with an attachment. Two concurrent calls to `POST /api/chat` resulted in a race where one would fail.

## Admin settings — model picker (2026-05-21)

### D4.admin-model-picker — three-role picker with capability icons

- **Decision**: Admin → Settings now shows three separate model pickers (interview, extraction, synthesis), each with a description, requirement chips, and a row of required capability icons.
- **Why**: All three roles have materially different requirements (latency vs. accuracy, tool use, long context) and should use different models. A single picker assumed one model for all tasks.

### D4.openrouter-capability-fields — correct API field names

- **Decision**: `GET /api/admin/models` proxies OpenRouter's `/models/user` endpoint and uses `architecture.input_modalities`, `architecture.output_modalities`, and `supported_parameters` to derive capability flags.
- **Why**: The initial implementation used `architecture.modality` (a string like `"text+image->text"`) and `supported_generation_params` — both fields don't exist in the actual API response. The correct fields are arrays: `input_modalities: ["text","image","file"]`, `output_modalities: ["text"]`, `supported_parameters: ["tools","tool_choice","structured_outputs",...]`.
- **Why `/models/user` not `/models`**: `/models/user` returns only the models the API key has been granted access to (the account guardrail), so admin dropdowns show only the models we can actually call. The public `/models` endpoint returns all of OpenRouter's catalog — thousands of models the key may not have access to. An earlier revision incorrectly used `/models` under the belief that `/models/user` stripped capability metadata; that assumption was wrong and has been corrected.
- **Tool use detection**: `supported_parameters.includes("tools") || supported_parameters.includes("tool_choice")`. No regex fallback needed once the correct field names are used.



---

# AI Architecture Retrofit — R1 through R4 (2026-05-25)

## D5.provider-native-architecture — Big 3 direct, not OpenRouter

- **Decision**: All future production AI calls go through `OracleAIClient → ContextCompiler → ModelRouter → Provider-Native Adapter`. Adapters are direct (`@anthropic-ai/sdk`, `@google/genai`, `openai`); OpenRouter is deprecated for production work.
- **Why**: OpenRouter abstracts away the exact caching primitives — Anthropic explicit breakpoints, Vertex explicit cached content, OpenAI prefix caching with task-specific keys — that make the difference between sub-cent and multi-cent extraction over high-volume batches. For a system that will run extraction workers over thousands of messages a day, that compounds.
- **Alternative ruled out**: Continue using OpenRouter + Vercel AI SDK. Rejected because the abstraction destroys cache observability and locks us out of provider-native structured-output formats.
- **Scope**: Established R1 (curated route catalog with strict 1 Primary + 1 Fallback per role) through R2 (the OracleAIClient pipeline itself). Real SDK calls land in R3+ adapter wiring; R2 ships typed stubs that throw `ProviderAdapterNotImplementedError` so the router can fall back correctly even before the SDKs are pulled in.

## D5.default-interview-haiku — Haiku 4.5 default, not Sonnet

- **Decision**: `default_interview_route = anthropic_claude_haiku_4_5_interview_primary`.
- **Why**: An earlier doc revision proposed Sonnet 3.5 as the primary interview route. For a pre-production app ("not even 30% coded" per Albert), that's an unnecessary cost burden. Haiku 4.5 is the right cost-aware default; Sonnet is wired as the manual escalation route (`anthropic_claude_sonnet_interview_escalation`).
- **Promotion rule**: Sonnet can only become the default after eval data shows Haiku's interview quality is materially insufficient on POP Creations transcripts. Per `docs/oracle/06-evaluation-framework.md`, that decision must be recorded back here with the eval-run timestamp.

## D5.licensor-vendor-split — `licensor` is a first-class entity type

- **Decision**: `licensor` exists in `entities.entity_type` as a separate type from `vendor`. Operating-vendor subtypes are further split: `factory`, `freight_provider`, `testing_lab`, `packaging_supplier`, `service_provider`. The plain `vendor` value becomes a residual bucket.
- **Why**: POP Creations sells licensed entertainment products (Disney/Marvel/Star Wars/NBCUniversal/Warner Bros). Licensors govern approvals, art/brand rules, legal permissions, and style-guide constraints. Operating vendors govern capacity, lead times, customs paperwork. A query about *"when do Disney approvals need to happen before production"* must never retrieve generic factory manuals — and that requires structural separation, not prompt engineering.
- **Enforcement**: CHECK constraints on `entities.entity_type` and `entity_proposals.proposed_entity_type` (in `migrations/sql/12_taxonomy_constraints.sql`) enumerate the full whitelist. Boundary rules on `knowledge_top_domains` list `vendor_manual` / `freight_invoice` as default-excluded document classes for licensor questions.

## D5.boundary-rules-required — every top-domain has belongs-here / does-not-belong-here

- **Decision**: `knowledge_top_domains` is not just a name + display order. Every row carries `belongs_here`, `does_not_belong_here`, `common_entity_hints`, `default_excluded_document_classes`, and `neighboring_domain_ids`.
- **Why**: Without explicit boundary examples, the LLM has to infer domain boundaries from the domain name alone — which produces inconsistent tagging at scale. Boundaries are the contract the LLM is evaluated against in `segmentation` evals.
- **Source**: Added in commits `665201b` (doc) and `c529594` (schema + seed).

## D5.claim-metadata-two-columns — `tstzrange` → two timestamp columns

- **Decision**: `claim_metadata` uses `effective_from` + `effective_until` (two `timestamp` columns) rather than the spec sketch's `time_validity tstzrange`. `effective_until IS NULL` means "currently in effect". Half-open semantics: `[from, until)`.
- **Why**: Drizzle ORM doesn't model `tstzrange` cleanly; consumers would have to learn range overlap operators (`@>`, `<<`, etc.) instead of using ordinary `WHERE` clauses. The two-column form covers every case the spec needs and is the canonical Postgres pattern for half-open intervals.
- **Doc updated**: `docs/oracle/07-knowledge-segmentation.md` schema sketch updated in commit `fe60304` to match the actual schema.

## D5.candidate-status-consistency-checks — DB-level enforcement of pipeline invariants

- **Decision**: Added 13 CHECK constraints on the R4 staging tables, not just status whitelists. The named consistency rules are:
  - **`promoted-consistency`**: `extraction_candidates.status='promoted'` iff `promoted_at` and `promoted_to_claim_id` are both populated.
  - **`duplicate-consistency`**: `status='duplicate'` requires at least one of `duplicate_of_candidate_id` / `duplicate_of_claim_id` to be set.
  - **`sensitive-consistency`**: `status` in `(rejected_sensitive, quarantined_sensitive)` requires at least one of the three sensitivity flags to be TRUE — catches workers that quarantine without recording why.
  - **`validated-fields-required-on-pass`**: `extraction_candidate_evidence.validation_status` in `(exact_match, normalized_match)` requires the validated quote + offsets + timestamp to be non-null — no silent passes.
- **Why**: These invariants would be easy to violate from a worker that's partially refactored. Putting them in the DB means even hand-written admin SQL has to follow them. Spec 6.8's `claim_evidence_source_check` is the precedent.

## D5.legacy-claim-domains-preserved — backfill, don't replace

- **Decision**: `claim_top_domains` is backfilled from the legacy `claim_domains` table (Postgres enum-based) via `migrations/sql/42_claim_top_domains_backfill.sql`. The legacy table and the `knowledge_domain` Postgres enum are intentionally preserved.
- **Why**: The R3.5 acceptance gate explicitly requires that "the legacy `knowledge_domain` enum column on `claims` is still present and readable" during transition. R6+ migrates the read path; only then does a future cleanup migration drop the legacy table and enum.
- **Mapping table**: documented inline in `42_*.sql` (e.g., `licensing` → `licensing_approvals`, `coldlion` → `it_systems`, `sampling` → `product_development`, `general` → `customer_ops` residual). Backfilled rows carry `assignment_reason='backfill'` + `assignment_confidence=0.5` so admins can identify and reclassify them later.

## D5.r2-mock-mode — test-mode adapters auto-register

- **Decision**: `OracleAIClient({ mode: 'test' })` automatically registers `MockProviderAdapter` instances for all three providers. Production mode wires the real (stub) `AnthropicAdapter` / `VertexGeminiAdapter` / `OpenAIAdapter`.
- **Why**: The R2 smoke gate (`pnpm --filter @oracle/ai verify:r2`) needs to exercise the full pipeline (compiler → router → adapter → validator) without API keys or network access. Test mode keeps that single source of truth.
- **Production behavior unchanged**: production callers don't get mock fallback. If a stub adapter throws `ProviderAdapterNotImplementedError`, the router falls back to the configured Fallback route — it does NOT silently swap in mock output.

---

# AI Architecture Retrofit — R5 through R8 (2026-05-25, second pass)

## D6.pure-function-first — extraction logic split from DB executor

- **Decision**: All R5/R5.5/R6/R7 business logic lives in pure functions in `packages/oracle-engines/src/extraction/` (`validateQuote`, `decidePromotion`, `resolveEntity`, `validateTaxonomy`, `decideCircuitBreaker`, `decideCacheProfitability`, `computeCandidateHash`, `mapLegacyDomainsToTopDomains`, `estimateTokensForCache`). DB I/O is in thin wrappers (`executePromotion`, `recordCacheCreation`, `recordCacheTermination`, `recordCacheReuse`).
- **Why**: smoke gates run in milliseconds without API keys / DB / network access. 127 assertions across R2/R5/R5.5/R6/R7 verify business invariants in CI on any machine. Decision logic is auditable in 60 lines instead of buried in a 600-line transaction.
- **Alternative ruled out**: building stateful Worker classes that own the DB connection + the decision logic together. Rejected because it would force every smoke test to spin up Postgres and mock Drizzle's transaction interface, and would bury the "when does insert_new_claim become append_to_existing_claim" rule.

## D6.openrouter-bridge-adapter — transitional dispatch through OracleAIClient

- **Decision**: R6 / R7 / R8 construct `OracleAIClient` with `OpenRouterBridgeAdapter` wearing each provider hat (`anthropic`, `vertex`, `openai`) so calls dispatch through OracleAIClient correctly but the underlying network call goes to OpenRouter via the Vercel AI SDK.
- **Why**: satisfies the "everything through OracleAIClient" architectural rule (context-pack logging, `model_run_usage_details`, route resolution, fallback handling) without forcing `@anthropic-ai/sdk` / `@google/genai` / `openai` SDK dependencies into the install before there's a wet-test path for them.
- **Mapping**: route's `modelId` (e.g. `claude-haiku-4-5`) maps to OpenRouter's namespace (`anthropic/claude-haiku-4-5`); if `modelId` already includes a `/`, it passes through as-is.
- **Removal plan**: per-adapter replacement in R9+ as each worker that needs a specific provider's caching/structured-output gets refactored. R9 (synthesis) is the natural place to wire the Anthropic SDK first.

## D6.candidate-hash-column — historical duplicate detection

- **Decision**: R7 adds a nullable `claims.candidate_hash varchar(64)` column with a partial UNIQUE index `WHERE candidate_hash IS NOT NULL` (in `migrations/sql/14_claims_candidate_hash_unique.sql`). The promotion executor stamps the hash on insert and looks claims up by it INSIDE the advisory-locked transaction.
- **Why**: R6 shipped advisory locking but had no way to find an existing claim from a past cron run with the same hash. R7 closes the gap: two workers racing on the same hash now both see the same committed view inside their respective locks, the loser auto-upgrades to `append_to_existing_claim`. Historical claims (pre-R7) have NULL hash and don't collide with the partial UNIQUE.
- **Alternative ruled out**: a full UNIQUE constraint (without WHERE NULL). Rejected because it would require backfilling every historical row, which we can't do without recomputing the hash from the original validated quotes — they're not stored on `claims`.

## D6.race-safe-promotion — hash lookup inside the advisory lock

- **Decision**: `executePromotion` does the `existingClaimWithSameHash` lookup INSIDE the Drizzle transaction, after `pg_try_advisory_xact_lock(hashtextextended($1, 0))` returns. Pre-built decisions from R6 callers are honored except when the in-lock lookup detects a race — in that case an `insert_new_claim` decision is automatically upgraded to `append_to_existing_claim`.
- **Why**: pulling the lookup outside the lock re-introduces the race window. Inside the lock, the executor sees the latest committed view of the world; only one worker can be in the lock at a time per hash; the partial UNIQUE on `claims.candidate_hash` is the belt to the lock's suspenders.
- **R5 callers (R6 worker) still work**: they pre-build the decision and pass it. The executor will correct course if a race is detected. R7+ callers (document worker) pass `snapshotInputs` instead so the executor re-decides entirely inside the lock.

## D6.cache-profitability-heuristic — explicit Vertex cache gating

- **Decision**: `decideCacheProfitability` encodes the rule from `docs/oracle/02-provider-native-ai-architecture.md` exactly: `useExplicitGeminiCache = (sourceTokenEstimate >= 25_000 && expectedReuseCount >= 3) OR (sourceTokenEstimate >= 100_000 && expectedReuseCount >= 2)`. The large rule takes precedence when both apply.
- **Why**: Vertex explicit caches bill while they exist. Creating one for a one-off small chunk is a net cost loss — the storage fee outpaces the saved input-token spend. The heuristic captures the break-even points conservatively.
- **R7 worker behavior**: document ingestion makes one call per document by default, so the heuristic almost always returns `skip_explicit_cache` today. The bookkeeping path (`recordCacheCreation` / `recordCacheTermination`) is wired and tested, so when multi-pass extraction lands later the cache lifecycle audit trail just works.

## D6.cache-lifecycle-tracking — `provider_cached_content` always recorded

- **Decision**: Every explicit cache, real or notional, gets a `provider_cached_content` row at creation (`recordCacheCreation`) and a termination row update (`recordCacheTermination`) when its reuse window ends. The CHECK constraint `deleted_at IS NULL iff status='active'` is enforced at the DB level.
- **Why**: caches that aren't tracked become orphaned billing items. The bookkeeping path is identical whether the underlying cache is a real Vertex resource or a stub — when `@google/genai` is wired in a later phase, the lifecycle audit trail already works.
- **Status whitelist** (`migrations/sql/11_observability_constraints.sql`): `active | deleted | expired | failed | orphaned`. Workers MUST drive transitions through `recordCacheTermination`; direct UPDATEs are still possible but the CHECK constraint catches inconsistent rows.

## D6.providerOptions-escape-hatch — chat-route tool calling without leaking SDK types

- **Decision**: R8's chat route needed multi-turn message history + tool calling + `stopWhen` + `temperature` — none of which fit `OracleAIClient.runText`'s narrow single-system-single-user contract. The fix: add an optional `providerOptions?: Record<string, unknown>` field on `GenerateTextArgs` / `RunTextArgs`. The bridge adapter spreads it into the underlying `generateText` call.
- **Why**: avoids leaking Vercel AI SDK's `ToolSet` type into the OracleAIClient surface (which would force every adapter to either implement or ignore tool calling). The escape hatch is generic on purpose — each adapter opts in to specific keys.
- **Backward compat**: R2 smoke (16 assertions) still passes because the field is optional. Mock + stub adapters ignore it.
- **Removal plan**: when the surface stabilizes (probably after R9 + R10), the `providerOptions` field can be narrowed into typed members (`tools`, `messages`, `temperature`, etc.) without breaking callers.

## D6.legacy-claim-domains-still-preserved (extended through R6/R7)

- **Extension to D5.legacy-claim-domains-preserved**: R6 and R7 workers now write to `claim_top_domains` via `executePromotion` (insert_new_claim path). The legacy `claim_domains` table is no longer written to by the new pipeline — but it's still preserved in the schema and still readable, per the R3.5 acceptance gate. The backfill SQL (`42_claim_top_domains_backfill.sql`) populates `claim_top_domains` from the legacy table on every migrate so the transition stays consistent.
- **Removal plan**: drop `claim_domains` + the `knowledge_domain` Postgres enum only after R9 + R10 are wired and the admin dashboard reads exclusively from `claim_top_domains`.

---

# AI Architecture Retrofit — R9 through R10.5 (2026-05-25, third pass)

## D7.synthesis-unsupported-name-check — deterministic, not LLM-graded

- **Decision**: R9's `validateSynthesisDiff` rejects synthesis output if `updatedMarkdown` mentions a capitalized proper-noun-shaped name that is NOT backed by either an approved claim summary OR the canonical entity registry. The check is a pure deterministic regex + lookup, not an LLM grader.
- **Why**: provenance must be auditable. An LLM judge for "is this name supported" reintroduces the paraphrase trap R5 solved for quotes — the judge can drift, the failure isn't reproducible, and the rejection isn't explainable to admin. The regex approach is conservative: false positives hold the synthesis for admin review (acceptable), false negatives let fabricated names through (worse), so the stopword list is curated tight.
- **Implementation**: heading lines are stripped before scanning because headings are structural metadata, not factual claims. Code blocks, inline code, and markdown link URLs are stripped before regex matching. Sentence-start stopwords (A, An, The, Although, ...) and calendar words (Tuesday, January, ...) are explicitly whitelisted. Multi-word capitalized phrases are matched as one candidate so "Walt Disney" is checked as a unit, not as separate tokens.
- **Removal plan**: none. This is a load-bearing safety net.

## D7.rejected-version-row — preserve failed synthesis without changing currentVersionId

- **Decision**: When R9 synthesis validation fails, the worker INSERTS a `brain_section_versions` row with `reviewStatus='rejected'` carrying the failed markdown + structured `validationFailures` + `unsupportedNames` in `structuredContent`. `brain_sections.currentVersionId` is NOT updated. Existing `brainSectionReviewStatusEnum` already had `'rejected'`, so no schema change.
- **Why**: "store failed synthesis output for review" (retrofit packet R9 task 10) requires durable inspection of what the model produced. Dropping the row loses the audit trail. Auto-applying the failed output to `currentVersionId` exposes broken synthesis to production reads. Inserting + not pointing at it is the in-between that satisfies both.
- **Alternative ruled out**: a separate `brain_synthesis_failures` table. Rejected because the existing schema already supports this case via the enum value — adding a parallel table would scatter the synthesis history across two tables and force every admin query to UNION them.

## D7.r10-dashboards-are-read-only — no actions, no new schema, no new dependencies

- **Decision**: All 6 R10 admin pages under `/admin/ai/*` are read-only. Server-rendered Drizzle queries against existing R3/R3.5/R4/R7 surfaces. No new tables, no new server actions, no new client libraries.
- **Why**: observability dashboards are a substitution for "wire instrumentation everywhere"; the instrumentation is already in the schema (R3 view, R4 staging, R7 cache tracking). The pages just have to show it. Adding actions or new schema would risk introducing bugs in the observability path itself.
- **Removal plan**: none. The pages will grow filters and exports as the data matures, but the read-only constraint is the invariant that keeps them lightweight to maintain.

## D7.r10-candidates-sensitive-exclusion-at-sql-level — privacy guarantee, not UI toggle

- **Decision**: The `/admin/ai/candidates` page filters out `rejected_sensitive` and `quarantined_sensitive` candidates from EVERY non-explicit tab via the SQL `WHERE` clause. The `"all"` tab uses `WHERE status NOT IN ('rejected_sensitive','quarantined_sensitive')`. Sensitive rows are reachable only via the explicit "Sensitive (hidden by default)" tab.
- **Why**: per `docs/oracle/03-candidate-before-claim-validation.md` ("Sensitive rejected/quarantined candidates must not appear in this standard queue"), PII / HR conflict / disciplinary material must NEVER leak into the standard admin queue. A UI-only toggle would let a misclick expose them; the SQL-level structural exclusion makes that impossible.
- **Removal plan**: none. This is a privacy guarantee.

## D7.r10.5-no-auto-mutation — every taxonomy change is admin-gated

- **Decision**: The R10.5 re-evaluation worker writes ONLY to `taxonomy_proposals`. No `INSERT INTO knowledge_top_domains`, no `UPDATE claim_top_domains`, no other taxonomy table modification. The admin approval flow (server actions in `apps/web/app/admin/taxonomy/_actions.ts`) is the ONLY path that can mutate taxonomy.
- **Why**: per `docs/oracle/07-knowledge-segmentation.md` ("the system should NEVER auto-mutate taxonomy"). Auto-promotion of clustering output would corrupt the registry with whichever model run happened to fire. Compact admin proposal cards mean the admin can vet changes in seconds without reading raw evidence.

## D7.r10.5-create-top-domain-applied-inline-others-queued

- **Decision**: The R10.5 server action `approveTaxonomyProposal` applies `create_top_domain` proposals INLINE in the same transaction as the approval audit. For other proposal types (`merge_top_domains`, `split_top_domain`, `reassign_claims`, `create_sub_topic`, `merge_sub_topics`, `split_sub_topic`, `retire_sub_topic`), the proposal is marked approved with a `taxonomy_change_log` entry of `changeType='approve_pending_reclassification_<type>'`. The actual reclassification mutation is queued for the dedicated reclassification job (R10.5 task 4).
- **Why**: `create_top_domain` is a single-row INSERT with no claim-level mutation needed. The other types require targeted `claim_top_domains` / `claim_sub_topics` moves + optional Brain synthesis re-runs — exactly the work the reclassification job exists to do correctly. Applying them inline in the approval server action would couple admin UI latency to a potentially large reclassification + risk partial-write bugs if the action times out.
- **Audit trail**: every queued approval gets a `taxonomy_change_log` row noting `queuedFor: 'taxonomy-reclassification-worker'`, so the admin sees in `/admin/taxonomy/change-log` what's been approved-but-not-yet-applied.
- **Removal plan**: when the reclassification job lands, the queued approvals get drained automatically.

## D7.r10.5-reevaluation-worker-deferred-clustering-body

- **Decision**: The R10.5 scheduled worker `taxonomy-reevaluation` ships with a scaffolded body that counts approved claims per active top-domain and reports an activation threshold (default 30 claims). It does NOT do clustering, drift detection, or proposal writing yet. `proposalsWritten: 0` is intentional.
- **Why**: without real claim density, the clustering body would be implementing an algorithm against synthetic data with no way to verify correctness. The scaffold + job_runs telemetry gives admin a clear "we're not there yet" signal instead of silently writing meaningless proposals that pollute the review queue.
- **What's documented inline**: the worker file's header documents exactly what the clustering pipeline does once it lands — per-domain density clustering on stored claim embeddings → cluster naming via cheap synthesis call → overlap analysis against current sub-topic centroids → drift detection per claim → cross-domain pattern check → proposal writing. Each step is a substitution for the current early-exit path.
- **Removal plan**: replace the early-exit with the clustering body when approved-claim density justifies it (the `domainsReady` count in the worker output tells admin when that point is reached).

## D7.openrouterbridge-still-bridges-after-r9 — wet-test gate before SDK swap

- **Extension to D6.openrouter-bridge-adapter**: After R9, every legacy `getOpenRouter()` worker call site has been refactored to dispatch through `OracleAIClient`, but ALL of those callers still bridge to OpenRouter via the `OpenRouterBridgeAdapter`. The real `@anthropic-ai/sdk` / `@google/genai` / `openai` SDKs are still not wired.
- **Why now**: the architectural rule ("everything through OracleAIClient") is satisfied. Swapping in real provider SDKs requires a wet-test path — cloud credentials, a test transcript, ability to compare provider responses. Pre-wet-test, the bridge ensures the entire pipeline runs identically; post-wet-test, the bridge gets swapped one adapter at a time as each provider's native features (Anthropic cache breakpoints, Vertex explicit caching, OpenAI structured outputs) are needed.
- **Sequence**: R9 (synthesis) is the natural place to wire Anthropic direct first, because synthesis is cost-sensitive and Claude is the primary route.

---

# Promotion executor — race-safe in-lock snapshot (2026-05-26)

## D8.race-safe-snapshot-reread — full candidate snapshot re-read inside the advisory lock

- **Decision**: `executePromotion` now re-reads the candidate row AND its validated evidence inside the Drizzle transaction, after the advisory lock is acquired. Callers no longer build a `CandidateSnapshot` outside the lock — they pass only `candidateId`, `candidateHash`, `modelRunId`, and `auxiliaryInputs` (which carries the caller-computed `taxonomy` validation result + optional `metadata`).
- **Why**: D6.race-safe-promotion got the hash lookup right but still trusted the caller's stale candidate/evidence snapshot. Two distinct races could fire there:
  1. **Same candidate already promoted by another worker** — the caller's snapshot still showed `status='validated'`, the hash lookup found no existing claim (because the other worker's promotion was a different candidate-id but the same hash) OR found one (if it was the same candidate row), and the executor would try to insert duplicate evidence with stale offsets. Now: the in-lock re-read sees `status='promoted'`, `decidePromotion` returns `reject(already_promoted)`, no insert attempted.
  2. **Evidence rows mutated** — the caller saw N validated evidence rows; another worker added an (N+1)-th between the caller's read and the executor's lock acquisition. Caller's snapshot promoted only N rows; the (N+1)-th was orphaned. Now: the in-lock re-read picks up the full current set.
- **Distinction between race scenarios** (important — the docs previously conflated these):
  - *Same* candidate re-read and found `status='promoted'` → `reject(already_promoted)` (the in-lock candidate-state branch)
  - *Different* candidate, same canonicalized hash → `append_to_existing_claim` (the in-lock hash-lookup branch). The current candidate is still `validated`; we append our validated evidence to the existing claim and mark our candidate `duplicate`.

## D8.missing-candidate-no-validation-result-write — FK target absent

- **Decision**: If the candidate row is missing inside the lock (extremely rare; would indicate a bug or manual delete), the executor returns `recorded_rejection` with `appliedDecision.reason='invalid_state'` WITHOUT writing to `extraction_validation_results`. Every other `reject` branch writes the audit row; this branch is the explicit exception.
- **Why**: `extraction_validation_results.candidate_id` has a FK to `extraction_candidates(id)`. Inserting an audit row pointing at a missing FK target would itself fail with a constraint violation, hiding the original anomaly behind a less-informative error. The caller logs the missing-candidate signal via `job_runs.error` and `model_runs.error`, which they already maintain; the audit row is gone but the signal isn't lost.
- **Documented in**: executor JSDoc + AGENTS.md §11 "Race-safe promotion" entry.

## D8.taxonomy-stays-caller-provided — registry drift NOT solved here

- **Decision**: `auxiliaryInputs.taxonomy` and `auxiliaryInputs.metadata` remain caller-computed and are NOT re-validated inside the lock. The in-lock re-read closes the candidate/evidence race; it does NOT close a hypothetical race between caller-side `validateTaxonomy()` and executor promotion where a `knowledge_top_domains` row gets retired or an `entities` row gets merged.
- **Why**: taxonomy + entity registry mutations only happen via admin approval through `/admin/taxonomy` server actions — which are admin-paced (minutes to hours), not worker-paced (milliseconds). The race window is human-scale; tolerating it until production traffic shows it actually fires is the right call. Re-running `validateTaxonomy()` inside every promotion lock would (a) couple unrelated registries to the lock window, (b) require the executor to depend on the entity registry + active top-domain set, and (c) add latency to every promotion for a race we have no evidence is real.
- **Removal plan**: if production traffic shows the drift race fires, the executor can be extended to re-validate taxonomy inside the lock against fresh `knowledge_top_domains` + `entities` SELECTs. The signature already supports it — `auxiliaryInputs.taxonomy` becomes optional input that the executor cross-checks rather than blindly trusts. Today it's blind trust.

## D8.executor-mappers-pure-and-tested — DB-row → snapshot mapping is unit-testable

- **Decision**: The two mappers — `mapCandidateRowToSnapshotCandidate(row)` and `mapEvidenceRowToValidatedEvidence(row)` — are exported from `promotion-executor.ts` and exercised by the R5 smoke gate (cases M1–M10, 23 assertions added). Pure functions; no DB access.
- **Why**: the executor's main risk after the refactor is field mapping (DB column names → snapshot field names, jsonb nullability, validation-status filtering). Without a live-DB test harness, the realistic protection is unit-level coverage of the mapping logic. The mappers ARE the mapping logic; testing them directly catches every realistic field-mapping bug before the executor SELECT even runs.
- **What's covered**:
  - undefined / null candidate row → null
  - happy-path candidate row → matching snapshot.candidate
  - confidence_score: null → undefined (NOT 0 or NaN — a regression here would silently downgrade impact scoring)
  - jsonb-null domains → []
  - non-array jsonb domains → [] (defensive against schema drift)
  - evidence with validation_status='exact_match' + populated validated_* fields → included with all fields mapped
  - evidence with validation_status='failed' → null (excluded from validated set)
  - evidence with validation_status='exact_match' but validated_exact_quote: null → null (defensive — refuses to fabricate values even though the CHECK constraint should prevent this row state existing)
  - evidence with validation_status='normalized_match' → included
  - all optional fields (pageNumber, confidence, the 3 employee FKs) pass through correctly

## D9.r-providers-raw-sdks-not-ai-sdk — Direct provider SDKs, no Vercel AI SDK wrappers

- **Decision**: R-providers wires `AnthropicAdapter` via `@anthropic-ai/sdk`, `VertexGeminiAdapter` via `@google/genai`, and `OpenAIAdapter` via the official `openai` SDK. The `@ai-sdk/*` Vercel AI SDK provider packages are explicitly NOT used inside `packages/ai/src/providers/`.
- **Why**: this is what D6 (and `docs/oracle/02-provider-native-ai-architecture.md` §"Shared architecture") already prescribe — "Adapters are direct (`@anthropic-ai/sdk`, `@google/genai`, `openai`); OpenRouter is deprecated for production work" and "No route handler or worker may call Anthropic, Google, OpenAI, **Vercel AI SDK**, or OpenRouter directly once the retrofit is complete." This decision records the brief detour during R-providers implementation where the adapters were first wired with `@ai-sdk/google-vertex` / `@ai-sdk/anthropic` / `@ai-sdk/openai` (commit `cf8f087`) and then reverted to raw SDKs (commit `bfc0821`) once the violation of D6 was noticed.
- **Why the @ai-sdk/* path was rejected**:
  - The Vercel AI SDK normalizes provider-specific cache fields (Anthropic's `cache_read_input_tokens`, Vertex's `usageMetadata.cachedContentTokenCount`, OpenAI's `prompt_tokens_details.cached_tokens`) through a uniform but lossy abstraction. Native fields land in `providerMetadata.{provider}.…` shape-shifted and renamed; the R7 cache lifecycle bookkeeping in `provider_cached_content` works much more cleanly against the raw SDKs.
  - Structured-output strategies differ across providers (Anthropic forced tool call vs. Vertex `responseJsonSchema` vs. OpenAI `response_format: { type: 'json_schema', strict: true }`). The Vercel AI SDK collapses all three into a single `generateObject` signature, which superficially looks like a win but takes away per-provider tuning knobs we want to use (strict mode, tool descriptions, schema relaxations for Gemini's OpenAPI dialect).
  - The decision precedent in D6 was already explicit; reading the docs first would have prevented the detour.
- **Wet-test confirmation**: with the raw SDKs wired and the workers + chat route switched off `OpenRouterBridgeAdapter` (commit `51a33ff`), a single synthetic operational message produced 2 promoted claims through the full pipeline in 8.3s, with `model_runs.provider = 'vertex'` (not `'openrouter'`), real Vertex `provider_request_id` captured, and the candidate-before-claim guarantee held end-to-end.
- **OpenRouterBridgeAdapter status**: retained as inert code with no production import. Slated for deletion in a follow-up cleanup once the four direct call sites have a few production days under load.

## D10.live-interjection-on-by-default — Both interjection paths post live messages from R11

- **Decision**: With R11.2 + R11.3 landed, both proactive interjection paths POST real chat messages by default:
  - `lull-interjection` task (every-minute cron) drafts a question and posts it whenever `decideLullInterjection` returns `'ask'`.
  - `contradiction-watcher` posts a chat-shaped surfacing question whenever `decideContradictionInterjection` returns `'live'` AND a channel can be resolved from `claim_evidence`.
  - `settings.enable_live_contradiction_interjections = true` (flipped by `50_enable_live_contradiction_interjections.sql`).
- **Why**: the original `enable_live_contradiction_interjections=false` default was conservative for an Oracle that hadn't yet been gated by the full validation pipeline. After R11 the gates are: severity=high AND detectionConfidence ≥ 80 AND cooldown ≥ `oracle_cooldown_minutes` AND under `max_oracle_interjections_per_hour` AND a model-suggested question exists AND a channel can be resolved. That stack is strict enough that the silent-default would suppress legitimate operationally-important contradictions; the user's call (HANDOFF 2026-05-26) was to flip it on and let admins observe the first week of behavior.
- **Alternatives ruled out**:
  - Dry-run logging only (write to `oracle_interventions` with `was_live_interjection=false` and `interjection_message_id=null`). Rejected because the audit trail already exists either way — the question is whether real users see the Oracle's drafts. If they don't, admin review remains theoretical and the gap-question loop never closes.
  - Keep `enable_live_contradiction_interjections=false` until production traffic. Rejected because the wet-test that this gate would block is *exactly* the production traffic; deferring means R11 ships but does nothing real.
- **Removal plan if misfires happen**:
  - `UPDATE settings SET value = 'false'::jsonb WHERE key = 'enable_live_contradiction_interjections';` — and the contradiction-watcher immediately respects it. Worker doesn't need to be redeployed; the setting is read on every claim-check.
  - For the lull task, the comparable kill switch is `enable_group_chat_lull_questions=false` (already implemented at the decider level — DMs bypass this).
  - If a per-channel kill switch is needed, the right shape is a new `channel_settings` table; today's settings are global.
- **Tuning knobs**:
  - `lull_window_seconds` (default 60). Lower for chatty channels, higher for slow ones.
  - `oracle_cooldown_minutes` (default 10).
  - `max_oracle_interjections_per_hour` (default 3).
  - `CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD` (constant in `packages/oracle-engines/src/interjection.ts`, default 80). Adjustable for the next phase if confidence-vs-misfire trade off needs shifting.

## D11.lull-interjection-round-1-simplifications — Topical relevance + presence are round 2

- **Decision**: R11.2 ships with two known simplifications that the user's HANDOFF decisions explicitly accepted as round-1 trade-offs:
  - **Presence (`isAnyoneTyping`) hardcoded to `false`.** A real Supabase Realtime presence query against `presence_state` was out of scope for R11. The risk: the Oracle may post a question while a human is mid-keystroke.
  - **Top-relevant-open-gap = highest-priority gap with targetEmployeeId null or a channel participant.** Embedding-based topical relevance (gap embeddings vs recent message embeddings) is out of scope for R11. The risk: the gap chosen may be in a domain the channel wasn't discussing.
- **Why both are acceptable round 1**:
  - The rate-limiting + cooldown stack ensures any single misfire is at most 3/hour and at least 10 minutes apart per channel.
  - The first batch of approved claims (just 2 from the wet-test) doesn't yet justify the engineering of embedding-similarity scoring against a sparse gap corpus.
  - Admin sees every interjection via `oracle_interventions` + `/admin/ai/runs?taskType=lull-interjection` and can identify both classes of misfire and feed that into the round-2 prioritization.
- **Round 2 work** (already on the HANDOFF "What's next" list):
  - Wire `supabase.realtime.presenceState()` into the lull task before computing `isAnyoneTyping`.
  - Add a `gaps.embedding` column + populate it at gap-creation time, then score by cosine similarity against the mean embedding of the channel's recent messages.
- **Removal plan**: both round-1 shortcuts disappear when round 2 lands. Until then, they are explicit `// round 1` comments in `apps/workers/src/trigger/lull-interjection.ts`.

## D12.deepseek-and-qwen-adapters — Two new direct-provider adapters added (2026-05-27)

- **Decision**: Add `DeepSeekAdapter` ([packages/ai/src/providers/deepseek-adapter.ts](packages/ai/src/providers/deepseek-adapter.ts)) and `QwenAdapter` ([packages/ai/src/providers/qwen-adapter.ts](packages/ai/src/providers/qwen-adapter.ts)) to the production adapter map, expanding `OracleProvider` to `'anthropic' | 'vertex' | 'openai' | 'deepseek' | 'qwen'`.
- **Why**: Admin user requested DeepSeek (V3, R1) and Alibaba Qwen as selectable model families for the per-stage pools. Both expose mature, cost-competitive models with capabilities OpenAI/Anthropic don't (R1's reasoning at much lower cost; Qwen-max's large context).
- **API surfaces chosen**:
  - DeepSeek: `https://api.deepseek.com` (their own OpenAI-compatible endpoint). Auth: `DEEPSEEK_API_KEY`. Cache hits live in DeepSeek-specific `prompt_cache_hit_tokens` (NOT OpenAI's `prompt_tokens_details.cached_tokens` shape) — handled in `normalizeUsage`.
  - Qwen: DashScope **US** OpenAI-compatible endpoint `https://dashscope-us.aliyuncs.com/compatible-mode/v1` (this is the only OpenAI-compat surface; `dashscope-intl.*` and `dashscope.aliyuncs.com` are the native-API endpoints). Auth: `DASHSCOPE_API_KEY`. Native DashScope SDK rejected for now — overhead of a less-mature SDK doesn't justify the marginal explicit-cache control gain. Can swap to native later if cost analysis warrants.
- **Naming**: provider keys `deepseek` and `qwen` match OpenRouter's slug convention, so the existing enrichment lookup (with dash→dot normalization) finds them without extra logic.
- **Per D6/D9 compliance**: Direct provider APIs only — neither adapter touches OpenRouter for inference. OpenRouter is still pricing/capability enrichment only.
- **Schema impact**: Migration 56 relaxes the `model_capabilities.provider` CHECK constraint to allow the two new values.
- **Refactor opportunity taken**: Replaced 7 hand-rolled `adapters: { anthropic: new ..., vertex: ..., openai: ... }` blocks (1 chat route + 6 workers) with a single `buildStandardAdapters()` helper ([packages/ai/src/client/standard-adapters.ts](packages/ai/src/client/standard-adapters.ts)). Future provider adds touch one file. The helper is tolerant of missing env vars — a missing DEEPSEEK_API_KEY no longer breaks the entire OracleAIClient boot for endpoints that don't need DeepSeek.
- **Round-1 trade-offs documented**:
  - DeepSeek `generateObject` uses `response_format: { type: 'json_object' }` (free-form JSON + Zod validation) rather than strict json_schema, because DeepSeek doesn't expose strict json_schema mode. Risk: malformed JSON is caught by Zod, not by the model itself. Falls back to schema_repair internal subroute on validation failure.
  - Qwen via OpenAI-compat has no client-controlled prompt cache. Cache strategy `qwen_none`. Native explicit caching deferred until a use case justifies the native SDK swap.
- **User actions required**: Set `DEEPSEEK_API_KEY` and `DASHSCOPE_API_KEY` in Vercel env (all 3 targets) + local `.env.local` for the workers to dispatch to these models. Without keys set, the adapters are silently omitted from the standard map; admin pool selections still work (you just can't pick a DeepSeek/Qwen model as a default).

## D13.catalog-model-filtering — blocklist + quality gates for model catalog (2026-05-28)

- **Decision**: The OpenAI model source (`packages/ai/src/model-capabilities/sources/openai.ts`) uses a **blocklist** of non-chat model categories rather than an **allowlist** of chat model name prefixes. Two post-enrichment quality filters apply globally to ALL 5 providers in `refreshModelCatalog()`: (1) drop models with no pricing AND no capability flags; (2) drop models priced ≥ $15.01/1M input tokens.
- **Why blocklist over allowlist**: The allowlist required a manual code change every time OpenAI released a new model generation — GPT-5.x was invisible until `gpt-5` was explicitly added to the prefix list. A blocklist of known non-chat categories (audio, image, realtime, TTS, transcription, moderation, video, legacy completion) passes new chat generations automatically without a code change.
- **Blocklist details** (`sources/openai.ts`): prefixes `gpt-audio`, `gpt-image`, `gpt-realtime`, `chatgpt-image`, `omni-moderation`, `sora`, `tts-`, `dall-e`, `babbage`, `davinci`, `ada`, `curie`, `text-embedding`, `text-moderation`, `text-search`, `text-similarity`, `whisper`; substrings `-tts`, `-transcribe`, `-diarize`, `-translate`, `-search-api`.
- **Quality filter rationale**: OpenRouter's enrichment catalog doesn't know about many dated API snapshots, model aliases (`chat-latest`), or very new/niche models. A model with no pricing AND no capability flags is effectively useless in the admin picker — admins can't evaluate it and it can't be budget-controlled. The ≥$15.01/1M input price cap removes models outside the operational budget range without per-model manual exclusion.
- **Observed counts after first refresh**: 118 OpenAI API models → 73 after blocklist → ~58 after quality filters. Full 5-provider totals: ~155 DB rows → ~100 after quality filters on next full refresh.
- **Files**: `packages/ai/src/model-capabilities/sources/openai.ts` (blocklist), `packages/ai/src/model-capabilities/index.ts` (post-enrichment filters).
- **Do not revert to allowlist**: An allowlist silently excludes every new model family until manually updated; a blocklist misclassifies at most a few edge cases (e.g. a new modality variant with an unfamiliar prefix) which are easy to add to the blocklist on discovery.

## D14.batch-api-support — adapter-level Batch API for async ~50% off pricing (2026-05-28)

- **Decision**: The `OracleProviderAdapter` interface gains two **optional** methods: `submitBatch(args)` and `retrieveBatch(args)`. Adapters that don't implement them are unchanged. Round 1 wires Batch APIs on **OpenAI** (`client.batches.create` + JSONL via `client.files`), **Vertex Gemini** (`client.batches.create` with GCS-backed JSONL I/O), and **Anthropic** (`client.messages.batches.create` + `.results()` streaming JSONL; landed 2026-05-28). DeepSeek and Qwen are deferred — DeepSeek has no public batch API; Qwen's batch surface is non-OpenAI-compatible and would require a native DashScope SDK swap, which D12 already deferred.
- **Why**: Provider Batch APIs run async (24-hour SLA) at ~50% the sync price. Oracle's claim-extraction worker runs on a 4-hour cron with no live-response constraint — exactly the workload Batch APIs target. At the volume of operational chat extraction, the discount compounds.
- **Provider-agnostic contract**: All batch shapes flow through generic types in `packages/ai/src/providers/types.ts`:
  - `SubmitBatchArgs { route, requests: BatchRequest[], jsonSchema?, providerOptions? }`
  - `BatchRequest { customId, plan, providerOptions? }` — `customId` is caller-supplied and echoed back in results
  - `SubmitBatchResult { providerBatchId, providerMetadata }` — opaque metadata persists to `provider_batch_jobs.provider_metadata_json`
  - `RetrieveBatchResult { status, results?, requestCount?, completedCount?, failedCount? }` where `BatchStatus = 'submitted' | 'in_progress' | 'completed' | 'failed' | 'expired' | 'canceled'`
- **Why this contract avoids leaking provider-specific shapes**: OpenAI uses file IDs, Vertex uses GCS URIs, Anthropic uses inline payloads. Each provider stuffs whatever it needs into `providerMetadata` (opaque JSON); the caller persists it verbatim and passes it back. The adapter is the only code that interprets the metadata bag.
- **Anthropic specifics** ([packages/ai/src/providers/anthropic-adapter.ts](packages/ai/src/providers/anthropic-adapter.ts)): builds one `{custom_id, params}` entry per request and posts via `client.messages.batches.create`, where each `params` is a full `MessageCreateParamsNonStreaming` (same shape as a sync `messages.create`). For structured output, attaches the forced single-tool `output_structured` per request (mirrors `generateObject`). Retrieve maps `processing_status: ended` → `'completed'` and streams `client.messages.batches.results(id)` (JSONL); per-item `result.type` (`succeeded` / `errored` / `canceled` / `expired`) drives `BatchResultItem`. `providerMetadata = {}` — the batch ID alone is sufficient. No GCS / file-upload prerequisite.
- **OpenAI specifics** ([packages/ai/src/providers/openai-adapter.ts](packages/ai/src/providers/openai-adapter.ts)): builds JSONL with one line per request (`{custom_id, method:'POST', url:'/v1/chat/completions', body}`), uploads via `client.files.create({purpose: 'batch'})`, creates batch via `client.batches.create({input_file_id, endpoint, completion_window: '24h'})`. `providerMetadata = { inputFileId }`. Retrieve downloads the output file (also JSONL) and pairs lines by `custom_id`.
- **Vertex specifics** ([packages/ai/src/providers/vertex-gemini-adapter.ts](packages/ai/src/providers/vertex-gemini-adapter.ts)): writes JSONL to `gs://$GOOGLE_VERTEX_BATCH_GCS_BUCKET/oracle-batch-<uuid>/input.jsonl`, submits batch with `src` + `dest` GCS URIs. Vertex output doesn't echo per-request IDs, so `providerMetadata` includes `customIdsInOrder: string[]` — output lines are matched to customIds by index (Vertex preserves input order). Requires `GOOGLE_VERTEX_BATCH_GCS_BUCKET` env var; throws clearly if unset.
- **DB schema** (migration `60_batch_jobs.sql`):
  - New `provider_batch_jobs` table: one row per submitted batch. Columns include `provider`, `provider_batch_id` (provider's external ID), `status` (`submitted|in_progress|completed|failed|expired|canceled`), `task_type`, `route_id`, `model_id`, `request_count`, `completed_count`, `failed_count`, `provider_metadata_json`, `submitted_at`, `poll_last_at`, `completed_at`, `results_retrieved_at`.
  - `extraction_batches.provider_batch_job_id` (nullable FK) links per-input rows to the owning batch job. Only set in batch-mode runs.
  - `model_runs.dispatch_mode varchar(20)` ∈ `'sync' | 'batch' | NULL` — for cost dashboards to reflect the 50% discount on batch rows.
- **Round 1 scope (landed 2026-05-28)**: foundation + full worker integration. Schema, adapter contract, OpenAI + Vertex + Anthropic `submitBatch`/`retrieveBatch`, two-phase worker (`claim-extraction-batch-submit.ts` + `claim-extraction-batch-drain.ts`), shared `processSegmentOutput` extracted from `claim-extraction.ts`, `extraction_dispatch_mode` settings gate at the top of all three tasks. Migration 60 applied to prod. Default is `'sync'` until an admin flips it.
- **Cost tracking note**: when the worker integration lands, batch-dispatched `model_runs` rows must have `dispatch_mode = 'batch'` and their `cost_usd` computed against the 50%-discount rate. The catalog enrichment doesn't carry batch pricing separately — apply the multiplier client-side in the cost computation.
- **Vertex GCS bucket requirement**: a one-time admin task. Create a regional GCS bucket in the same region as your Vertex deployment (`us-central1`), grant the `oracle-trigger-worker@vertex-ai-497120` service account `roles/storage.objectAdmin`, set `GOOGLE_VERTEX_BATCH_GCS_BUCKET` in Vercel + Trigger.dev env. Buckets-per-environment is fine — preview deploys can share the prod bucket since each batch object name is UUID-prefixed.

## D15.recall-live-teams — Live Teams participation through Recall.ai (2026-06-04)

- **Decision**: Add an optional Recall.ai live Teams path. `/api/teams/live/start` creates a Recall bot with real-time transcription (`elevenlabs_streaming` first, `assembly_ai_v3_streaming` fallback). `/api/teams/live/recall` verifies Recall signatures and triggers `teams-live-recall-utterance`, which stores finalized utterances as `messages`, gates Oracle interjections, and posts short questions back to Teams chat through Recall.
- **Why**: Microsoft Graph still has no live Teams transcript stream. Native Microsoft app-hosted media bots would require an infrastructure exception. Recall externalizes the media/STT layer while The Oracle keeps its source-of-truth and validation architecture unchanged.
- **Scope rule**: Live utterances are evidence-shaped `messages` rows, not claims. They enter candidate-before-claim like every other message. Post-call Graph transcript ingestion remains the canonical backstop for complete transcripts.
- **Safety rule**: The worker ignores STT partials and acts only on finalized `transcript.data` utterances. It applies a cheap keyword gate before calling the interview model, then uses the existing interjection cooldown/rate-cap settings before posting.

## D-transcript-fuzzy-quote — fuzzy quote match for spoken transcripts (2026-06-04)

- **Decision**: `validateQuote` gains an opt-in `allowFuzzy` path. After strict verbatim + normalized matching fail, if the model quote's content tokens overlap the source utterance by >= `fuzzyMinOverlap` (default 0.5), accept as `normalized_match` (method `fuzzy_token_overlap`) and anchor the stored evidence to the REAL source utterance text, not the model's paraphrase. Enabled only on the message/transcript path (`claim-extraction.ts`); documents stay strict.
- **Why**: First real conversation to hit extraction was a Teams call. Spoken transcripts are disfluent and the model paraphrases them, so the polished quote never appears verbatim — strict matching rejected ~every transcript claim. Product-owner call (2026-06-04) to loosen for spoken sources.
- **Auditability**: deterministic token check (no LLM grader), and evidence stays a real transcript span — only the "model must reproduce verbatim" requirement is relaxed. Partially overrides the "no fuzzy" note in quote-validator.ts / docs/oracle/03. Knobs: fuzzyMinOverlap (0.5), >=4-token floor.

## D-raw-transcripts — persist raw VTT for re-runnability (2026-06-04)

- **Decision**: Persist each call's raw WebVTT in `raw_transcripts` at ingestion (idempotent on transcript_id). Hand-written `migrations/sql/62_raw_transcripts.sql`; worker uses raw `sql`, not in schema.ts.
- **Why**: `messages` are a lossy transform (merged turns, resolved speakers, dropped timing) and Microsoft expires ad-hoc transcripts. Raw VTT keeps the whole pipeline re-runnable from true source for iterative fine-tuning.

## D-transcript-approval-gate — human approval before transcript extraction (2026-06-24)

- **Decision**: Teams transcripts are ingested as `extraction_status='awaiting_approval'` (new enum value; `migrations/sql/75`) and held until an admin approves them at `/admin/transcripts`. `raw_transcripts.approval_status` (`migrations/sql/76`) tracks the decision; approve flips the channel's messages → `pending`, reject → `skipped`. The extraction cron is unchanged (it only ever selects `pending`).
- **Why**: Albert wanted to review meeting transcripts before they produce claims, rather than the prior auto-ingest-then-review-at-claim-level flow. Lowest-blast-radius gate — no extraction-worker change.

## D-scheduled-meeting-transcripts — capture scheduled meetings, not just ad-hoc (2026-06-24)

- **Decision**: Add a second standing subscription on `communications/onlineMeetings/getAllTranscripts` alongside the ad-hoc one (`ensureAllSubscriptions` keeps both alive via the existing `teams-subscription-renew` cron — no new schedule, respecting the 10/10 limit).
- **Why**: Only ad-hoc "Meet Now" calls were being captured; normal scheduled meetings (the common case) produced nothing — last real transcript was 2026-06-04.

## D-meeting-picker — discover meetings, choose which to ingest (2026-06-24, supersedes D-transcript-approval-gate)

- **Decision**: The Oracle does NOT auto-ingest meetings. Available meetings are discovered as metadata only — by the webhook (real-time, `discovered_via='subscription'`) and the on-demand `teams-transcript-discovery-scan` task (past meetings, `'scan'`) — into a new `meeting_transcripts` table (migration `77`). An admin picks meetings on `/admin/transcripts`; picking triggers `teams-transcript-ingestion`, which pulls the VTT, writes `messages` as `extraction_status='pending'` (auto-extract), anchors timestamps to the real meeting time, and flips the row to `ingested`.
- **Why**: The gate was at the wrong stage — it auto-ingested every transcript then gated *extraction*. The product need is to choose, from a list, which meetings get pulled in *at all*. Anchoring to real meeting time also stops `lull-interjection` from treating an ingested past meeting as a live conversation (it was spawning spurious gaps/interventions).
- **Deprecated by this**: the `awaiting_approval` enum value (migration 75) and `raw_transcripts.approval_status` columns (migration 76) are now unused. Left in place (removing a PG enum value is disruptive; the columns are harmless); do not build on them.

## D-fail-loud-model-routing — approved pools replace hidden fallbacks (2026-06-25)

- **Decision**: Remove route-level fallback targets and hard-coded worker fallback routes. Pipeline stages resolve an ordered candidate chain from the selected primary plus the DB-approved pool; auxiliary slots (`vision`, `general`, `translation`) are explicit single-pick settings. When all candidates fail or a slot is unset, the call fails loud.
- **Why**: A selected provider/model could silently run an unapproved fallback model when an adapter was missing or misconfigured, making cost, provenance, and capability debugging misleading. The approved pool is the only acceptable fallback chain because admins can inspect and edit it.
- **Observability**: `model_run_attempts` records each attempted route, including failed primary attempts and successful non-primary attempts. Admin pages show a banner when recent failed or non-primary attempts exist.
- **Capability guard**: Runtime resolution checks `model_capabilities` against slot requirements while `settings.enforce_model_capabilities=true`. Set it false only for controlled debugging.

## D-conversation-aware-message-extraction — whole conversations, non-quotable carry-in (2026-06-26)

- **Decision**: Message extraction no longer pulls a global `LIMIT(100)` and then segments the truncated set. Sync and batch extraction share `selectPendingConversations`, which selects whole same-channel conversation segments bounded by the 60-minute gap heuristic and stops at `extraction_char_budget` / `BATCH_SIZE` only between conversations.
- **Why**: Operational claims often emerge from a multi-message discussion. Cutting at an arbitrary global count can split the connected context and cause missed or distorted claims.
- **Provenance rule**: Prior same-channel messages are included only as non-quotable carry-in context (`extraction_carry_in_count`). The active segment's message IDs remain the only valid evidence sources, so quote validation still rejects claims that cite carry-in context.
- **Oversized conversations**: If one conversation exceeds the configured budget, process it whole and log the oversized condition rather than silently truncating it. Future work can add a more sophisticated sliding-window strategy if real conversations exceed model limits.

## D-macro-understanding-boundary — source outlines guide extraction, not evidence (2026-07-02)

- **Decision**: Add a macro-understanding layer in conservative slices. It stores provisional document `source_outlines`/`source_groups`, claim-level `claim_kind`, reviewable `macro_relationships` with `macro_relationship_claims` support links, and `source_coverage_findings`. Admins can generate outlines, extract/review macro relationships, run staleness sweeps, manually author relationships from approved support claims, drop stuck support, and convert coverage findings into gaps.
- **Trust rule**: Source outlines and groups are non-quotable guidance. They can help extraction resolve workflow shape, acronyms, handoffs, branches, and likely lenses, but they cannot create approved knowledge by themselves. Atomic claims still require exact quotes from `document_chunks` or source messages, and quote validation remains the enforcement boundary.
- **Macro relationship rule**: Durable macro relationships cite validated claim IDs, not raw model interpretation. Any Brain/chat/MCP helper that serves approved macro relationships must verify every support claim is currently `approved` at read time; relationship status alone is not trusted.
- **Operational guardrails**: No new Trigger.dev schedule is introduced while the project is at the schedule limit. New macro tables are server-only/service-role surfaces in this slice; RLS is enabled without anon/authenticated policies. Vector columns can exist now, but expensive vector indexes must follow the existing gated `ORACLE_RUN_VECTOR_INDEXES=1` convention.

# Document ingestion: Word, image vision, auxiliary models, context (2026-06-14)

## D-image-vision-two-pass — transcribe images to text before extraction

- **Decision**: Uploaded images (PNG/JPEG/WebP/HEIC) are ingested in two passes. Pass 1 (`transcribeImageToText` in `document-ingestion.ts`) calls a vision model to render the image to faithful text — a structured text topology for diagrams (nodes `[Shape/Color: "label"]`, edges `[A] --(cond)--> [B]`, swimlane `### headers`), with verbatim labels kept inside the nodes. Pass 2 is the unchanged chunk → extract → quote-validate → promote pipeline run over that text.
- **Why**: Every claim's `exactQuote` must validate against a `document_chunk`. An image has no text to validate against, so a single-pass "image → claims" call would force bypassing quote validation and break the candidate-before-claim provenance guarantee. The transcription becomes the chunk text; the verbatim-label rule keeps quotes matchable. The topology output (vs free-form prose) gives the extractor un-scrambled structure.
- **Provider path**: Inline image input is implemented in the Vertex adapter (`toVertexParts` → Gemini `inlineData`, guard `verify:vertex-inline-image`); the worker formats the image part per provider (Gemini/Anthropic/OpenAI). Inference is provider-direct (`@google/genai`), never OpenRouter. The file-backed Vertex cache is skipped for images (a lone image is below the cache token minimum).

## D-auxiliary-models — single-pick models outside OracleModelRole

- **Decision**: Admin-selectable models that are not one of the 3 strict pipeline roles (vision, general-purpose, translation) are "auxiliary models" defined in a registry (`packages/ai/src/routes/auxiliary.ts`, `AUXILIARY_MODELS`) and resolved by `resolveRouteCandidates(db, id)` as explicit single-pick slots. `OracleModelRole` stays frozen at `interview | extraction | synthesis`. The settings page, picker, and `/api/admin/models` iterate the registry; none special-case auxiliary ids.
- **Why**: Pipeline roles carry structure auxiliary models don't (stage requirements, approved model pools, batch dispatch). Folding vision into `OracleModelRole` would ripple through every `Record<OracleModelRole, …>` map. The registry adds the next utility model with one entry and no new branches.
- **Setting**: `default_vision_route` (+ `default_vision_reasoning_effort`), `default_general_purpose_route`, and `default_translation_route` are seeded with `ON CONFLICT DO NOTHING`. Unset means configuration error, not fallback.

## D-admin-document-upload — company docs decouple from chat channels

- **Decision**: `POST /api/admin/documents` (admin-only, multi-file) uploads knowledge documents directly from Admin → Documents with no channel — it stores the file, inserts a `documents` row, and triggers `document-ingestion`. The channel-based `POST /api/documents` remains for chat attachments.
- **Why**: There is no UI to create a chat channel (channels are only created by the Teams flows / admin raw-import), so the channel-coupled uploader made company-doc upload unreachable. `documents` has no channel dependency — the worker reads by id — so decoupling is clean and is the correct model for company/process knowledge.

## D-document-context-and-hints — uploader context as a soft signal

- **Decision**: `documents` gains nullable `context` (text) and `domain_hints` (jsonb of `knowledge_top_domains.id`). `context` is injected into both the extraction prompt and the Pass-1 image-vision prompt; `domain_hints` are rendered as a non-binding prior. Per-claim `domain_valid` stays authoritative — hints never force or override classification, which stays per-claim (a document legitimately spans multiple domains).
- **Migration nuance**: shipped via hand-written `migrations/sql/65_document_context_and_domain_hints.sql` (idempotent `ADD COLUMN IF NOT EXISTS`) AND added to `schema.ts`, but with no Drizzle-generated migration. So `db:check-drift` may flag it and a fresh-DB `db:migrate` won't recreate the columns unless `sql/65` is applied. Consistent with the `raw_transcripts` hand-written precedent; fold into a generated migration if drift is undesirable.

## D-business-process-domain — cross-functional process knowledge (2026-06-14)

- **Decision**: Add `business_process` as a top-level domain for end-to-end company workflows, operating model overviews, and cross-functional handoff maps. The legacy extractor still emits the old `general` enum value, so new extraction maps `general` to `business_process` instead of the former Customer Operations residual.
- **Why**: Whole-company process docs should not be buried under a single department, and broad questions such as "how does our overall process work?" should retrieve overview claims plus relevant department-specific process claims. The retrieval planner now expands broad process queries across `business_process` and neighboring process domains rather than depending on a global fallback.
- **Prompt change**: Extraction prompt version `2.0.1` tells the model to classify by operational meaning, not literal department keywords, and to use `general` for cross-functional/end-to-end workflow claims while also adding narrower domains when a claim materially belongs to them.
- **Follow-up prompt change**: Extraction prompt version `2.0.2` lets document ingestion use `document_chunks.id` as `sourceMessageId` and formats document input as labeled chunks. This keeps document quote validation strict while giving the model an exact source ID and reducing quotes that cross persisted chunk boundaries.

## D-document-ingestion-windowing — no silent document truncation (2026-06-15)

- **Decision**: Large uploaded documents are extracted through `buildDocumentChunkWindows()` in `apps/workers/src/trigger/document-ingestion.ts`. Each model call remains bounded, but the worker iterates every persisted chunk window and aggregates the results instead of truncating the document to the first N characters.
- **Why**: `business-process.md` was a 42,420-character Markdown document. The old first-15k-character cap made the upload appear to complete while extracting only the beginning of the process. Raising the cap into one giant call caused provider structured-output validation to fail. Windowing keeps calls reliable without losing later sections.
- **Quote policy**: Text/Markdown document quote validation uses `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`, which normalizes formatting syntax such as emphasis, headings/lists, links/images, inline code ticks, and table separators. It is deterministic formatting normalization only; document extraction still rejects paraphrases, fuzzy matches, and cross-chunk quotes.
- **Entity policy**: Unknown-only entity taxonomy results are allowed to promote while staging entity proposals. Invalid domains, ambiguous domains, and entity type mismatches still block promotion.
- **Verified production run**: Trigger worker `20260615.4` reprocessed document `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` (`business-process.md`) in run `run_cmqehatni237e0un5ioyywuez`: 12 chunks, 155 extraction candidates, 139 promoted pending-review claims, 16 rejections, document status `complete`.
- **Future sessions should**: Keep document windows aligned to whole `document_chunks.id` values, avoid reintroducing a document-level cap, and remember that newly promoted document claims are not retrievable by chat/synthesis until reviewed and approved.

## D16.claim-correction-lessons — approved revisions steer future extraction (2026-06-15)

- **Decision**: Extraction prompt version `2.1.0` includes a semi-stable "reviewer correction lessons" block built from approved claim revisions. `packages/ai/src/prompts/claim-correction-lessons.ts` reads `claim_review_events` where `action='revise'` and the replacement claim is `approved`, formats compact before/after examples plus recurring correction rules, and the sync message worker, batch-submit worker, and document-ingestion worker include it in their `OraclePromptPlan`.
- **Why**: Reviewer notes and revised claims do not magically train the model. The immediate, auditable feedback loop is to feed approved correction patterns back into the next extraction calls while preserving the original AI output and the human-approved replacement.
- **Boundary**: The lesson block is guidance only. It is not claim evidence, not Brain source material, and not fine-tuning. The candidate-before-claim validators still enforce quote provenance, taxonomy validity, sensitivity gates, and promotion rules.
- **Admin surface**: `/admin/ai/claim-lessons` shows counts, recent approved correction pairs, and the exact prompt block extraction will see.
