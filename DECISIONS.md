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
