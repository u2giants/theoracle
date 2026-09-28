# S02 preview dispatch — exact inputs for independent technical review

Owner request (Albert, Claude chat, 2026-09-28): "approve two synthetic-only
Trigger preview projects for Oracle S02". This file is the exact action set a
reviewer approves or refuses. Nothing here is executed until a VERDICT APPROVE.

## Actions

1. Create Trigger.dev project `oracle2-extract-preview` in org POP
   (`cmpdjy8yg0107n50hqma87hjk`). Create project `oracle2-project-preview` in the
   same org. Legacy `proj_wgpzsvhmsopqhvwqaycn` is not touched.
2. Set environment variables on the **staging** environment of each project only.
   All values are synthetic; hosts use the reserved `.invalid` TLD and are never
   reachable. No Supabase, provider, or 1Password production credential is used.
   - Extractor: `ORACLE2_MODE=synthetic`, `ORACLE2_ENVIRONMENT=preview`,
     `ORACLE2_DATABASE_URL=postgresql://oracle2_extract:synthetic@db.invalid:5432/oracle2`,
     `ORACLE2_CANDIDATE_GRAPH_URL=redis://candidate.invalid:6379`,
     `ORACLE2_WORKSPACE_ALLOWLIST=00000000-0000-4000-8000-000000000002`,
     `ORACLE2_DAILY_BUDGET=1`, `ORACLE2_TELEMETRY_MODE=off`.
   - Projector: same mode/environment/allowlist/budget/telemetry,
     `ORACLE2_DATABASE_URL=postgresql://oracle2_project:synthetic@db.invalid:5432/oracle2`,
     `ORACLE2_CONFIRMED_GRAPH_URL=redis://confirmed.invalid:6379`,
     `ORACLE2_PROJECTION_SIGNING_KEY=<48 random bytes, generated locally, piped, throwaway>`.
3. Deploy `apps/workers/trigger.oracle2-extract.config.ts` and
   `trigger.oracle2-project.config.ts` from PR #45's exact head to staging.
4. Trigger the synthetic extractor task, measure build size, cold start and exit;
   trigger a second run and cancel it; trigger the projector and record that it
   runs without candidate credentials and fails closed at the unreachable store.
5. Record project refs, versions and sanitized results in S02-dependencies.md.

## Out of scope

No hosted Postgres or FalkorDB is created, so no FalkorDB server runs under SSPL
here; the SSPL deployment verdict is requested separately for S03 hosting. The
projector's successful clean exit against a live store stays proven only in CI.
Rollback: delete both projects; nothing else changes.
