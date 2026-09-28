# S02 preview dispatch — exact inputs for independent technical review

Owner request (Albert, Claude chat, 2026-09-28): "approve two synthetic-only
Trigger preview projects for Oracle S02". This file is the exact action set a
reviewer approves or refuses. Nothing here runs before a `VERDICT APPROVE` whose
record names the reviewed commit; the operator deploys **only that commit**
(checked with `git rev-parse HEAD`) and re-requests review if it changes.
Revision 1 was refused (qwen plan review, 2026-09-28); this revision fixes H1–H3,
M1–M5, M8, M9 and L1–L3.

## Preconditions

- `ai-task-gates check --before infrastructure` passes, then `--before deploy`.
- CI on the reviewed commit passes, including workers typecheck and
  `scripts/oracle2/verify_worker_bundle.mjs` (script paths resolve inside the
  deployed `scripts` glob).
- Org plan unchanged: projects use the existing POP org plan; no paid-tier change.
  If Trigger requires one, stop.

## Actions

1. Create, via Trigger MCP `create_project_in_org` (org POP,
   `cmpdjy8yg0107n50hqma87hjk`), projects named
   `dedicated-oracle2-extractor-preview` and `dedicated-oracle2-projector-preview`
   (same vocabulary as `dev/oracle2/runtime-identities.yaml`). Record both refs.
   Legacy `proj_wgpzsvhmsopqhvwqaycn` is never touched.
2. Set **staging** environment variables through the management API
   (`POST https://api.trigger.dev/api/v1/projects/<ref>/envvars/staging`) with the
   PAT in 1Password item "Trigger.dev Personal Access Token (management)", read by
   `op` into a pipe, never printed. Values are synthetic; hosts use the reserved
   `.invalid` TLD and are unreachable; every store URL carries a synthetic password
   (now required outside local/test by `config.py`).
   - Common: `ORACLE2_MODE=synthetic`, `ORACLE2_ENVIRONMENT=preview`,
     `ORACLE2_WORKSPACE_ALLOWLIST=00000000-0000-4000-8000-000000000002`,
     `ORACLE2_DAILY_BUDGET=1`, `ORACLE2_TELEMETRY_MODE=off`.
   - Extractor only:
     `ORACLE2_DATABASE_URL=postgresql://oracle2_extract:synthetic@db.invalid:5432/oracle2`,
     `ORACLE2_CANDIDATE_GRAPH_URL=redis://:synthetic@candidate.invalid:6379`.
   - Projector only:
     `ORACLE2_DATABASE_URL=postgresql://oracle2_project:synthetic@db.invalid:5432/oracle2?connect_timeout=5`,
     `ORACLE2_CONFIRMED_GRAPH_URL=redis://:synthetic@confirmed.invalid:6379`,
     `ORACLE2_PROJECTION_SIGNING_KEY=` 64 hex characters from
     `openssl rand -hex 32`, piped into the API body, throwaway, never stored.
3. From `apps/workers` at the reviewed commit, with
   `ORACLE2_EXTRACT_TRIGGER_PROJECT_REF` and `ORACLE2_PROJECT_TRIGGER_PROJECT_REF`
   set to the two new refs and `TRIGGER_ACCESS_TOKEN` piped from the same PAT:
   `pnpm run deploy:oracle2-extract` and `pnpm run deploy:oracle2-project`
   (sync Python package, then `trigger.dev@4.5.15 deploy --config <file> --env staging`).
   Both configs set `retries.default.maxAttempts: 1`, so one trigger is one attempt.
4. Trigger on staging (Trigger MCP `trigger_task`):
   - Extractor `oracle2-synthetic-run`, payload
     `{"contract_version":1,"run_id":"00000000-0000-4000-8000-0000000000a1","workspace_id":"00000000-0000-4000-8000-000000000002","actor_id":"00000000-0000-4000-8000-000000000003","source_id":"00000000-0000-4000-8000-000000000004","source_revision":1,"mode":"synthetic"}`.
     Expected: completed, output `{"run_id":"…a1","status":"accepted_synthetic"}`.
   - Same payload with `run_id` `…a2`, cancelled while queued or executing.
     Expected: status CANCELED, no retry attempt.
   - Projector `oracle2-synthetic-project`, empty payload. Expected: FAILED after
     one attempt; stderr last line `{"status":"failed","error":"<ExceptionClass>"}`
     (fail closed at the unreachable store), no URL or secret in output.
   Record build image size, deploy version, cold-start (queued→executing and
   executing→completed durations) and attempt counts from `get_run_details`.
5. Write the sanitized results to `docs/verification/oracle2/S02-preview-result.json`
   and summarize them in `S02-dependencies.md`; set `preview_status` in
   `runtime-identities.yaml`; add both projects to
   `docs/agents/09-container-and-service-inventory.md` and
   `docs/oracle2-environment.md`. The preview gate is recorded manually (the
   `verify_phase.py` live mode stays refused until a store-backed preview exists).

## Out of scope

No hosted Postgres or FalkorDB is created, so no FalkorDB server runs under SSPL
here; the SSPL verdict is a separate S03 hosting question. The projector's
successful clean exit against a live store stays proven only in CI.
Rollback: delete both projects; nothing else changes.
