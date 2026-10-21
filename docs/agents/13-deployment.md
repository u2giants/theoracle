<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob b5e39e1305331da62607e6aae51de8c2ffdfe884 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 13. Deployment

Current deployment path:

- GitHub repo: `u2giants/theoracle`
- CI workflows: `.github/workflows/pr-check.yml`, `.github/workflows/task-gates.yml`, and `.github/workflows/oracle2-contracts.yml` (self-hosted; includes workers typecheck and the legacy worker-bundle guard)
- Web deploy target: Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`
- Worker deploy target: Trigger.dev project `proj_PRIVATE_REFERENCE_SHA256_9f596b7f49dd981243eda05436fe11207bc7a91b39b7806c41a831504c04bb01`
- Database/auth/storage target: Supabase project configured through env

How deployment works today:

1. Merge or push to `main`.
2. GitHub Actions runs `pr-check.yml`: installs dependencies, runs `verify:vercel-contract`, builds `@oracle/web`, runs retrieval parity, entity-aware retrieval, network-free Chinese retrieval, China translation review, Vertex file-cache, MCP, Vertex inline-image, auxiliary defaults, R0 reader, R1 cross-shape, taxonomy, and isolated fresh-database guards, then runs `pnpm db:check-drift` against production (requires `PROD_DIRECT_URL`; skips gracefully if absent). The credentialed `verify:chinese-retrieval-live` command is a separate release gate and never runs in CI.
3. Vercel auto-deploys the web app from GitHub using `vercel.json`.
4. Trigger.dev workers are deployed manually with `pnpm --filter @oracle/workers run deploy` (the `run` keyword is required — `pnpm` reserves the bare `deploy` form for its own subcommand).
5. Database migrations are applied manually with `pnpm db:migrate` before shipping code that depends on them. Hand-written `migrations/sql/*.sql` files MAY be applied via Supabase MCP `apply_migration`; generated `0NNN_*.sql` files MUST go through `pnpm db:migrate` (otherwise the journal drifts — see incident 2026-05-28).

Rollback:

- Web: promote a previous Vercel deployment.
- Workers: redeploy the previous commit forward (`git revert` or a clean checkout of the known-good commit, then deploy). Trigger.dev refuses to promote an older deployment — see `docs/deployment.md` §Rollback.
- DB: ship a compensating SQL migration; there is no automatic rollback layer.

Runtime env vars live in:

- Vercel project environment settings
- Trigger.dev project secrets/env
- local `.env.local`

SSH:

- SSH is not part of the normal deployment path.
- No VPS/container SSH workflow exists in this repo.

### Release & CI/CD policy (the rules that actually apply here)

The retained application uses managed Vercel web, Trigger.dev workers and Supabase DB/auth/storage. The W11 isolated native documentary runtime now has a proposed container release path, pending exact independent architecture/release review and live admission: GitHub source → immutable GHCR image → Coolify-owned app namespace. Its documentary image and isolated topology have now been installed for public-invented acceptance only; [the current live record](../verification/oracle2/workflow/W11-native-installation-live.md) preserves exact stage proofs and remaining gates. No private/company native release or business acceptance is established. Host/OS changes remain in Ansible and no SSH deployment is authorized. Analytical PM4Py bundling remains separately unadmitted. The rules that apply:

- **Single-branch model: `main` is the only long-lived branch.** There are no staging or release branches and no promotion model. Short-lived branches with a pull request are used when a reviewed record or protected check requires one (for example `docs/operations/` dispatch records); every source change uses a dedicated current-upstream branch and normal pull request; never push directly to protected `main`.
- **One release path, repo-driven:** push to `main` → Vercel builds/deploys the web app from `vercel.json`; workers ship via `pnpm --filter @oracle/workers run deploy`; DB via `pnpm db:migrate`. No alternate routine deploy method.
- **Application checks verify; the native image workflow publishes immutable artifacts.** `pr-check.yml` only builds + runs static guards + checks migration drift, without deployment or publishing. `oracle-native-image.yml` builds PR images and publishes exact merged-main SHA artifacts to GHCR with provenance/SBOM; publishing does not admit or deploy a runtime. Actual Coolify release requires the assigned reviewer’s exact-source/input APPROVE and deployment gates. No workflow may SSH or hand-edit the host.
- **The deploy gate is native to Vercel's build.** `vercel.json` uses the short `pnpm run build:vercel` command because Vercel caps `buildCommand` at 256 characters. That root script runs these ten network-free guards before `@oracle/web build`: `verify:retrieval-filter-parity`, `verify:chinese-retrieval`, `verify:vertex-file-cache`, `verify:chat-attachment-safety`, `verify:claim-translation-review`, `verify:eval-results-dashboard`, `verify:provider-capability-parity`, `verify:model-coverage-conversion`, `verify:lull-topical`, and `verify:mcp`. `verify:vercel-contract` protects the length and exact delegation contract in CI. The credentialed `verify:chinese-retrieval-live` and `verify:attachment-fallback-live` commands are separate and never run in Vercel.
- **Repo is authoritative; the platform owns runtime.** Runtime env vars / secrets / domains live in Vercel / Trigger.dev / Supabase — never baked into CI shell commands, images, or committed `.env*` (except `.env.example`).
- **Schema changes only through the approved migration path** (`pnpm db:migrate` for generated `0NNN_*.sql`; Supabase MCP `apply_migration` for hand-written `sql/*.sql`). Never ad-hoc production schema edits as the normal path.
- **Traceability:** every production change is auditable from repo commit history + Vercel / Trigger.dev / Supabase deployment history.
- **Drift check is advisory.** The Drizzle migration-drift check needs prod DB creds and runs only in `pr-check.yml`, not in the Vercel build (the build has no prod DB access, by design). Migrations are applied manually via `pnpm db:migrate` anyway, so drift is a bookkeeping signal, not a runtime-breakage gate. Everything else (build + verify guards) is hard-gated in the Vercel build per the bullet above.

