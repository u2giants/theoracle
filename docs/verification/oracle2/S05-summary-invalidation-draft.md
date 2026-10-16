# S05 summary invalidation draft verification

Status: source-only draft; S05 and parent #24 remain unaccepted.

The isolated candidate carries the existing unmerged #133 building block on current upstream `97da85b630e79e1bc01ae02fd177cf15f8b8ebed`. Fact correction now invalidates the store's dependent summary cache automatically. Rebuilt summaries follow the replacement fact; unrelated summaries and historical as-of answers remain available. This is in-memory offline behavior, not persistent runtime integration or live proof.

Nine tests passed using `uv run --extra test pytest -q tests/test_identity_resolution.py tests/test_temporal_facts.py tests/test_summary_invalidation.py` from `services/oracle-brain`. Coverage includes repeat correction, invalidated rebuilt summaries and refused duplicate correction preserving a current summary. No source-private data, credentials, providers, employee contact or production actions were used.

## Process deviation for independent review

The existing draft commit was cherry-picked into the isolated candidate before task declaration and committer-identity verification. This sequencing was a process deviation; subsequent checks do not retrospectively authorize it. No new implementation edits or publication occurred before those checks. The current declaration is `code`; `ai-task-gates check --before review` passed, and `git var GIT_COMMITTER_IDENT` showed `Albert Hazan <u2giants@users.noreply.github.com>`. The implementation fix and tests were then committed. The reviewer must assess the exact complete candidate including this disclosure before publication. Original #133 branch/worktree ownership is preserved. No stage merge is requested.

Remaining: independent review, draft publication, full S05 admission/projection/workflow/API/UI and preview proof after predecessor acceptance. Existing live-proof checklist stays on #29.
