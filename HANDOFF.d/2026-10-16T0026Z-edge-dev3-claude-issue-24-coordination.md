# HANDOFF — Oracle overhaul coordination (parent #24), S03 graph answers + parallel building blocks

Session: Claude chat 1199a622-271b-43db-8f2c-052a8986b771 on edge-dev3, 2026-10-15 (America/New_York). Repo: https://github.com/u2giants/theoracle

## 1. Goal
Coordinate parent issue https://github.com/u2giants/theoracle/issues/24 to completion using parallel subagents. Current serial child: S03 https://github.com/u2giants/theoracle/issues/27.

## 2. Current state (verified)
Merged to main:
- PR #131 `7b23ec5` — S03 offline gate run (`verify_phase.py S03 --mode offline`: 60 passed), pilot browser test (6 passed), automated rubric record https://github.com/u2giants/theoracle/blob/main/docs/verification/oracle2/S03-pilot.md, DNS rollback note for oracle-graph.designflow.app. Old answer method scored 0/20.
- PR #136 `14866d4` — graph (FalkorDB) answer path; rubric 20/20 (threshold 19). Scorer now matches word forms (approves/approval).
- PR #137 `ba557b2` — graph answers wired into the consultant page; held-out dev 10/10; browser test for "no evidence found"; offline gate 67 passed.
- PR #138 `9bbffbe` — isolated PREVIEW worker project + free separate test database + branch-scoped preview site settings. Reviewer APPROVE: stepfun run 20261015T212930-2917998-19581 at 2da09239. Worker crash root cause "Fatal Python error: Illegal instruction" (CPU-specific wheel); fixed with portable build. Live preview proof passed with synthetic data: https://github.com/u2giants/theoracle/issues/27#issuecomment-6203453597 . Credentials stored in 1Password vault vibe_coding by that subagent.

Open DRAFT PRs (offline building blocks, synthetic only, reviewed, NOT merged because plan line 321 imposes serial stage order): #135 (S04, bug fixed: older re-upload becomes current), #133 (S05), #132 (S06), #134 (S10), #130 (S13, bug fixed: deletion wins when no retention rule). Each has a signed review comment.

Parent #24 updated with a signed coordinator comment.

## 3. What remains
- S03 business acceptance: company questions, employee messages, grading PAUSED; approval expired Oct 13, only Albert can renew.
- Staff review (Ilona, Jessica) deferred to the very end by Albert's Oct 15 rule.
- Remove preview test resources (#138) when #27 closes — listed on #27.
- S04 → S16 serial chain waits on S03 closing; then land the matching draft PR first in each stage.
- Known remaining gaps inside drafts: S05 summaries are not auto-invalidated on correction (needs a trigger in a later piece); S10 refresh retries are unbounded.

## 4. Tried and failed
- First preview enablement attempt stopped at gate: no exact resource existed (#27 comment 6201387159). Resolved by #138.
- Hosted worker died after ~5 s with no output; resolved (see §2).

## 5. Known test baseline
Full oracle-brain suite on main without local stores: `7 failed, 828 passed, 1 skipped, 303 errors`; two files fail to import (`No module named 'scripts'`: test_operating_model_restore.py, test_pm4py_integration.py). Pre-existing; unowned.

## 6. Next action
When Albert renews the S03 business approval, run the real-data preview journey on #27; otherwise nothing in S04+ can be closed. Do not merge the drafts ahead of their stage.

## 7. Verification
`gh pr view 138 --json state` → MERGED; preview proof comment above.

## 8. Safety
No production writes, no company/employee messages, no shared-db claims.

## 9. Retention
Delete this file once #27 closes and the drafts land or are superseded.

Posted by Claude chat 1199a622-271b-43db-8f2c-052a8986b771 on edge-dev3
