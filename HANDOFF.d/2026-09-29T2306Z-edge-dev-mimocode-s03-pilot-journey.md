---
issue: 24
status: OPEN
owner: next Oracle coordinator session
---

# S03 pilot journey code landed — real-data preview proof remains

## 0. Decisions only Albert can make

None pending. Process owner for S03 real-data preview: Ilona (licensing workflow), set by Albert 2026-09-28.

## 1. What this application is

Oracle (`u2giants/theoracle`): POP Creations' evidence-backed knowledge and consulting app. Parent program #24; plan `plan_oracle_consultant_overhaul.md` (STATUS first).

## 2. What this session set out to do

Implement S03 (#27): the thin document-to-consultation pilot journey — upload a process document, see the source-linked draft, correct a connection, confirm, ask a question, get a cited answer plus one explicitly hypothetical improvement experiment.

## 3. Current verified state

- Branch `feature/s03-pilot-journey`, PR #57 (commits `2eb2cb3`, `a1e0144`).
- Python: `oracle_brain/workflows/pilot.py`, `ingest/document.py`, `retrieval/pilot.py`, `consultant/pilot.py`, `knowledge/{admission,authority}.py`, `sql/002_pilot.sql`.
- Web: `apps/web/app/consultant/page.tsx`, API routes (sources/questions/runs/reviews), `lib/oracle2-client.ts`, `components/consultant/pilot-workspace.tsx`.
- Tests: `test_pilot_journey.py`, `test_review_concurrency.py`, extended `test_authority.py` (forged actors, out-of-scope grants, revoked parents, expired delegates, revocation racing confirmation). `test_provider_policy.py` unchanged (already covers gate cases).
- Playwright: `playwright.oracle2.config.ts`, `tests/oracle2/pilot.spec.ts` — upload → correction → confirmation → answer after page refresh.
- `verify_phase.py` supports S03; CI runs `verify_phase.py S03 --mode offline` after S02 gate.
- Python modules import OK; non-DB logic checks pass (3 blocks, retrieval, citations, hypothetical).
- Compose mounts `002_pilot.sql`; conftest installs both SQL files.

## 4. What did not work

- Local Postgres on Windows is unreliable (autovacuum crash 0xC0000142); full `verify_phase.py S03 --mode offline` needs the CI runner (edge-dev3) with Docker Compose stores.
- `ai-task-gates check --before pr` reports `unknown action: pr` — the CLI action vocabulary does not include "pr". Used `start --class code` at task declaration.

## 5. Key findings

- The existing `test_provider_policy.py` already covers all S03 gate cases for provider policy (unapproved fallback, changed endpoint/terms, expired scope, source text in telemetry).
- The S02 authority model (`appointments` table + `has_authority`) supports all five adversarial cases required by the S03 gate with minimal extension.

## 6. Exact next steps

1. Wait for CI on PR #57 to run `verify_phase.py S03 --mode offline` and confirm green.
2. Merge PR #57 per policy (documentation-only plan update may merge with `--admin`).
3. Open leftover-proof issue #58 is already created for the real-data preview journey with Ilona.
4. After merge: run the real-data preview journey (requires independent reviewer APPROVE for any preview infrastructure). Ilona reviews using S01 rubric. Record in `docs/verification/oracle2/S03-pilot.md`.
5. When real-data proof completes, update plan STATUS row S03 to ✅ and close #27 and #58.
6. Only then name S04 (#28) as next on #24.

## 7. Handoff hygiene

This file is the S03 baton. The session that completes the real-data preview proof deletes this file under the successor rule and writes its own. S02 handoffs (`2026-09-29T0251Z-edge-dev3-claude-s02-providers-release.md`) are retired: their work is on main and obligations are carried in the plan STATUS.
