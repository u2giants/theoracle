# S02 preview dispatch — exact inputs for independent technical review

Owner request (Albert, Claude chat, 2026-09-28): "approve two synthetic-only
Trigger preview projects for Oracle S02". This file is the exact action set a
reviewer approves or refuses. Nothing here runs before a `VERDICT APPROVE` whose
record names the reviewed commit; the operator deploys **only that commit**
(checked with `git rev-parse HEAD`) and re-requests review if it changes.
Revisions 1 and 2 were refused; revision 3 was approved and executed at
`d879495`, where the extractor build failed (Trigger's Python extension installs
Debian Python 3.11; the bundle needs 3.12). **Revision 4** reuses the two
already-created projects and their staging variables unchanged and changes only:
the build layer (`apps/workers/oracle2-python-extension.ts` installs Python 3.12
with digest-pinned uv 0.12.19 and hash-checked `uv pip install --require-hashes`,
replacing `@trigger.dev/python`'s apt layer; `runScript` still reads
`PYTHON_BIN_PATH`), and adds task `oracle2-synthetic-pause-resume` for the
plan's pause/resume proof. Steps 0-2 are already done (approval record on #26;
projects `proj_esmuwkezljvasptkbiwr`, `proj_jtaztxnmppzfchdsgvea`); step 0 is
repeated for revision 4 before step 3.

## Preconditions

- `ai-task-gates check --before infrastructure` passes, then `--before deploy`.
- CI on the reviewed commit passes. It now runs `test_preview_settings.py`
  (preview URLs need credentials; projector exits 1 with a sanitized JSON line
  and no secret) through `verify_phase.py S02 --mode offline`, the workers
  typecheck, and `scripts/oracle2/verify_worker_bundle.mjs` (script paths inside
  the deployed glob, TS identity guards equal the identity manifest, legacy
  config excludes both Oracle 2 tasks).
- Org plan unchanged: projects use the existing POP org plan; stop if Trigger
  asks for a paid-tier change.

## Actions

0. **Approval record before provisioning** (plan S02 row requirement): post on
   child #26 the reviewed commit, this file's path, the approving review file
   and verdict line, and the exact project names and org below. No step 1
   before that comment exists.
1. Confirm the org with Trigger MCP `list_orgs`: it must list `POP`, id
   `cmpdjy8yg0107n50hqma87hjk`, the org that owns legacy
   `proj_wgpzsvhmsopqhvwqaycn` (per `list_projects`). Then `create_project_in_org`
   (`orgParam` = that id) twice, names `dedicated-oracle2-extractor-preview` and
   `dedicated-oracle2-projector-preview` (vocabulary of
   `dev/oracle2/runtime-identities.yaml`). Record both refs. The Trigger MCP
   authenticates as the operator's logged-in Trigger user session, not a project
   key, so every later MCP call names `projectRef` and `environment: "staging"`
   explicitly; a call without both is not made. Legacy is never touched.
2. Set **staging** environment variables through the management API
   (`POST https://api.trigger.dev/api/v1/projects/<ref>/envvars/staging`) with the
   PAT in 1Password item "Trigger.dev Personal Access Token (management)", read by
   `op` into a pipe, never printed. Values are synthetic; hosts use the reserved
   `.invalid` TLD (expected NXDOMAIN; if a resolver answers, the store still fails
   closed on connect timeout). Every store URL carries a synthetic password.
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
     `openssl rand -hex 32`, piped into the API body with `isSecret: true` where the
     API accepts it; throwaway (no store is reachable, so nothing is ever signed),
     never stored, destroyed with the project.
3. From `apps/workers` at the reviewed commit, with
   `ORACLE2_EXTRACT_TRIGGER_PROJECT_REF` and `ORACLE2_PROJECT_TRIGGER_PROJECT_REF`
   set to the two new refs and `TRIGGER_ACCESS_TOKEN` piped from the same PAT:
   `pnpm run deploy:oracle2-extract` and `pnpm run deploy:oracle2-project`
   (sync Python package, then `trigger.dev@4.5.15 deploy --config <file> --env staging`).
   The build image chooses the Python interpreter; this deploy is the measurement
   of whether the pinned requirements install there. Build-time network: pypi.org,
   download.pytorch.org (CPU index), ghcr.io (uv image), and uv's Python
   download mirror; nothing runtime. **Stop rule:** if pip fails
   (for example no matching `torch` wheel), the image exceeds 4 GB, or the build
   exceeds 30 minutes, stop, record the failure, and fall back per the plan
   (qualified container host, separately reviewed) — no retry with changed pins
   under this approval. Both configs set `retries.default.maxAttempts: 1`.
4. Trigger on staging with Trigger MCP, always `projectRef` = the matching new
   ref and `environment` = `staging`:
   - `trigger_task` `oracle2-synthetic-run` on the extractor project, payload
     `{"contract_version":1,"run_id":"00000000-0000-4000-8000-0000000000a1","workspace_id":"00000000-0000-4000-8000-000000000002","actor_id":"00000000-0000-4000-8000-000000000003","source_id":"00000000-0000-4000-8000-000000000004","source_revision":1,"mode":"synthetic"}`.
     Expected: COMPLETED; output the string
     `{"run_id": "00000000-0000-4000-8000-0000000000a1", "status": "accepted_synthetic"}`
     plus a trailing newline (Python `json.dumps` default separators).
   - Cancel: `trigger_task` with the same payload and `run_id` `…a2`, options
     `{"delay": "10m"}` so the run is deterministically DELAYED; then
     `cancel_run` with its `run_…` id. Expected: CANCELED, zero attempts. Then a
     third run (`…a3`, no delay) cancelled with `cancel_run` immediately after
     `trigger_task` returns, recording whichever state it reached.
   - Pause/resume: `trigger_task` `oracle2-synthetic-pause-resume` on the
     extractor project, same payload with `run_id` `…a4`. Expected: COMPLETED
     with `before` and `after` both equal to the extractor output string, and the
     trace shows a 10-second wait between two Python executions.
   - `trigger_task` `oracle2-synthetic-project` on the projector project, payload
     `{}`. Expected: FAILED after one attempt; stderr last line
     `{"status": "failed", "error": "<ExceptionClass>"}`; no URL or secret.
   Measurements from `get_run_details` and the deploy output: deploy version,
   image size, build duration, queued→executing and executing→finished times,
   attempt counts, final statuses.
5. Record results in `S02-dependencies.md` (Markdown, like every file under
   `docs/verification/`) using only these fields: project names and refs, deploy
   versions, image size, build duration, per-run id, status, attempts, durations,
   and the exception class. Never paste env values, URLs, keys, or raw logs.
   Set `preview_status` in `runtime-identities.yaml` to `measured_synthetic` or
   `failed_synthetic` (allowed values: `not_provisioned`, `measured_synthetic`,
   `failed_synthetic`, `deleted`). Register the org id and both project refs in
   `docs/agents/08-data-model-and-external-identifiers.md`, and add both projects
   to `docs/agents/09-container-and-service-inventory.md` and
   `docs/oracle2-environment.md`. The preview gate is recorded manually; the
   `verify_phase.py` live mode stays refused until a store-backed preview exists.
6. Lifetime: both projects remain only until #26 closes, then are deleted and
   `preview_status` becomes `deleted`.

## Out of scope

No hosted Postgres or FalkorDB is created, so no FalkorDB server runs under SSPL
here (see `S02-dependencies.md`, preview decision); the SSPL verdict precedes
any FalkorDB hosting in S03. The projector's successful clean exit against a
live store stays proven only in CI. Rollback: delete both projects.
