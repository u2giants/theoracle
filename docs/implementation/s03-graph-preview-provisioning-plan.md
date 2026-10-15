# S03 graph-evidence preview provisioning plan (preview only)

Issue: [#27](https://github.com/u2giants/theoracle/issues/27) (S03, parent #24).
Purpose: close the blocker recorded on #27 (comment 6201387159): the graph-evidence
answer method (PR #137, `ba557b2`) has no hosted preview worker, no isolated hosted
database, and no preview-site settings, so it cannot be proven live.

This plan is the exact resource set an assigned AI reviewer approves. Nothing below
runs before `ai-task-gates check --before infrastructure --reviewer-approval <report>`
passes with an APPROVE naming the merged head of this plan.

## Hard limits

- Invented (synthetic) data only. No company questions, company documents, employee
  messages, grading or staff review.
- No production writes. Never touched: Supabase `eqccjfbyrywsqkxxpjvg` (Oracle
  production) or any other existing Supabase project; Trigger projects
  `proj_wgpzsvhmsopqhvwqaycn`, `proj_esmuwkezljvasptkbiwr`, `proj_jtaztxnmppzfchdsgvea`;
  Vercel Production or the shared Preview environment variables; FalkorDB confirmed.
- No new vendor. Platforms: existing Supabase account, existing Trigger org "POP",
  existing Vercel project `theoracle`, existing FalkorDB candidate on Coolify (hetz).
- No model/provider calls: worker runs `ORACLE2_ANSWER_ENGINE=graph-evidence` only;
  no OpenAI/OpenRouter key is set anywhere in this plan.
- Secrets move only through 1Password vault `vibe_coding` and pipes/0600 files under
  the session temp folder; never chat, arguments, logs or commits.

## Resources (exact)

| # | Resource | Platform / where | Cost |
|---|---|---|---|
| R1 | New Supabase project `oracle2-s03-preview`, region `us-east-1` | Existing Supabase org `gcxiglhgughlynvhdljs` ("Free"; has one free active slot) | $0 (free tier) |
| R2 | New Trigger project `oracle2-holistic-preview`, **staging** environment only | Existing Trigger org POP | existing plan |
| R3 | Vercel Preview env vars scoped by `gitBranch=oracle2-s03-preview` only | Existing Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | $0 |
| R4 | Git branch `oracle2-s03-preview` at the merged head of this plan (deploy trigger for R3) | GitHub `u2giants/theoracle` | $0 |
| R5 | One Vercel "Protection Bypass for Automation" secret, for scripted proof requests | Same Vercel project | $0 |
| R6 | Run-scoped FalkorDB graphs `oracle2_evidence_run_<runid>` (created and deleted by each answer) | Existing FalkorDB **candidate** (`oracle-graph.designflow.app:16391`, mTLS) | $0 |

No other resource is created or changed.

## Code in this PR (needed by the plan)

- `FalkorEvidenceGraph` accepts optional client-certificate TLS from
  `ORACLE2_GRAPH_TLS_CA_PEM`, `ORACLE2_GRAPH_TLS_CERT_PEM`, `ORACLE2_GRAPH_TLS_KEY_PEM`
  (all three, `rediss://` only; cert/key written once per process to 0600 temp files; hostname checked).
  The hosted FalkorDB requires a client certificate; without this the worker cannot
  connect. Unit test: `services/oracle-brain/tests/test_graph_tls_options.py`.
- `scripts/oracle2/seed_hosted_preview.py`: applies `001_foundation.sql`, `002_pilot.sql`,
  creates the five `oracle2_*` login roles directly with random passwords (the committed
  local passwords are never applied), applies `dev/oracle2/grant-postgres.sql`, seeds two invented documents (the same text
  as the reviewed browser fixture), a signed throwaway owner appointment and review/confirm
  delegation for one invented actor, and computes the exact corpus digest. It writes all
  generated credentials to a new 0600 file outside the repository *before* any database
  change, runs schema/roles/seed in one transaction, refuses a database that already has the
  `oracle2` schema, and accepts only `db.<ref>.supabase.co` or the Supabase pooler with user
  `postgres.<ref>`, with `sslmode=require`. Refuses any
  project ref other than the one passed, and all known existing refs.

## Settings (exact names; values from R1 seed output / 1Password)

R2 staging environment variables:
`ORACLE2_ENVIRONMENT=preview`, `ORACLE2_ANSWER_ENGINE=graph-evidence`,
`ORACLE2_TELEMETRY_MODE=off`, `ORACLE2_DATABASE_URL` (R1 pooler URL, role
`oracle2_holistic`), `ORACLE2_CANDIDATE_GRAPH_URL` (`rediss://:<candidate password>@oracle-graph.designflow.app:16391`),
`ORACLE2_GRAPH_TLS_CA_PEM` / `_CERT_PEM` / `_KEY_PEM` (candidate worker client TLS + private CA),
`ORACLE2_HOLISTIC_WORKSPACE_ID`, `ORACLE2_HOLISTIC_SOURCE_IDS`, `ORACLE2_HOLISTIC_CORPUS_DIGEST`.
Forbidden and verified absent: `ORACLE2_CONFIRMED_GRAPH_URL`, `ORACLE2_PROJECTION_SIGNING_KEY`,
`ORACLE2_CHECKPOINT_DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, any model key.

R3 Vercel Preview (gitBranch `oracle2-s03-preview` only):
`ORACLE2_DATABASE_URL` (R1 pooler URL, role `oracle2_pilot_web`), `ORACLE2_PILOT_TOKEN`
(random), `ORACLE2_PILOT_ACTOR`, `ORACLE2_PILOT_WORKSPACE_ID`,
`ORACLE2_HOLISTIC_TRIGGER_SECRET_KEY` (R2 staging secret key),
`ORACLE2_HOLISTIC_CORPUS_DIGEST`, `TRIGGER_API_URL=https://api.trigger.dev`.

## Steps

1. Create R1 via the Supabase Management API (PAT `Supabase CLI Personal Access Token`);
   generated DB password stored in 1Password `Oracle2 S03 preview DB - oracle2-s03-preview (<ref>)`.
2. Run the seed script against R1's admin URL; store its output JSON in the same
   1Password item. Record only non-secret ids and digest on #27.
3. Create R2; set R2 staging variables through the Trigger API; deploy
   `apps/workers/trigger.oracle2-holistic.config.ts` to staging from the merged head.
4. Create R4 at the merged head; set R3 variables; create R5 (stored in 1Password);
   wait for the branch preview deployment to be READY.
5. Live proof (below). Post signed evidence on #27.

## Live proof (success check)

Against the branch preview URL, with the bypass header and the pilot token:
1. Supported question "Who does Intake Lead send the packet to?" on the seeded source
   reaches `completed` with at least one citation whose quote is from `intake.txt`.
2. Unsupported question "What is the travel reimbursement limit?" reaches `completed`
   with no citations and `evidenceStatus=no_source_evidence` ("no evidence found").
3. Trigger staging runs for both are `COMPLETED`; FalkorDB candidate holds no
   `oracle2_evidence_run_*` graph afterwards.

## Rollback / teardown (when #27 closes or on any failure)

Delete R3 variables and R5; delete branch R4; delete Trigger project R2; pause then
delete Supabase project R1; confirm no `oracle2_evidence_run_*` graph remains on the
candidate FalkorDB; archive the 1Password item. Each is independent and reversible
up to deletion; nothing else depends on them.
