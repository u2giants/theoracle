# R2 source-bound final record correction plan

Status: **OPEN PLAN. IMPLEMENTATION, DEPLOYMENT, AND PRODUCTION ARE NOT AUTHORIZED.**

Plan: [`../plan_r2_source_bound_final_record_correction.md`](../plan_r2_source_bound_final_record_correction.md)

## 0. Decisions only Albert can make

### Blocking

- Decide whether to authorize local implementation of F0-F6. Recommendation: authorize it because
  the plan is source-only, GLM 5.2 found no serious issue, and every unsafe or dishonest result stops
  the work. This blocks all application-code changes.

### Already settled, do not re-ask

- 2026-08-11: do not deploy, run production, consume another production gate, weaken the verifier,
  restore hidden owner lookup, raise budgets, or enable merge/apply.
- 2026-08-11: rows 16, 24, and 26 are honest negative controls and must remain unsupported.

The next session must put the one blocking decision above to Albert in one message before editing
application code.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload documents and ask questions. Workers turn sources into exact-source duties and reviewable
knowledge. Repo: `C:\repos\oracle`; GitHub: `u2giants/theoracle`; branch: `main`; web:
`https://oracle.designflow.app`; Trigger.dev: `proj_wgpzsvhmsopqhvwqaycn`; Supabase:
`eqccjfbyrywsqkxxpjvg`.

## 2. What we set out to do, and why

Albert authorized writing and independently reviewing a local-only correction plan after the sole R2
production gate scored 19/30. The plan targets final record quality and incomplete exact-source seeds.
It does not authorize implementation.

## 3. Current state

- Reader code is pushed, CI-green, and deployed as worker `20260811.1`.
- Sole production map `37a8fc62-23e4-46b7-8464-d1c784dc73cd` scored 19/30.
- Eight rows have source-supported correction paths: 5, 14, 15, 17, 19, 20, 23, 29.
- Rows 16, 24, and 26 are negative controls. Row 24 says the team assists with downloading, which
  cannot honestly be rewritten as direct download without changing the action family.
- New plan: `plan_r2_source_bound_final_record_correction.md`; F0-F6 are all open.
- No application code, deployment, production, model, budget, matcher, DB, merge, or apply change has
  occurred under this plan.
- GLM 5.2 approved the corrected plan for Albert's implementation decision with no P0/P1 findings.
- Plan and first handoff version were committed at `8679a0513d13cb06d251e0865292cb04910687d8`.
- Fresh-session audit fixes were committed and pushed at
  `7b9c0fc92e4d9bb3050903b76510916272b52c9b` on `main`.
- GitHub Actions run `31532357283` passed for the final handoff commit.

## 4. Everything tried that did not work

1. Earlier model-first releases scored 11-19/30.
2. A hidden source-prefix fallback made local support look better by exposing invisible text. It was
   removed and must never return.
3. Local 28/30 proved source support, not live completion. Production still scored 19/30.
4. More budget is not justified because production left calls, tokens, and dollars unused.
5. Matcher aliases or weaker negation would hide bad stored fields rather than correct them.

## 5. Root causes and key findings

- Complete records can fail through inflected actions, missing named tokens, or exception text inside
  the object.
- Other exact-span duties stay incomplete after broad completion.
- Existing code has a narrow duty-verb stemmer; the plan reuses it.
- The unchanged source-support verifier has an honest ceiling of 28/30, with rows 16/26 failed.
- The separate final-record replay must also keep row 24 failed because assistance is not direct work.
- Local gate requires all 8/8 eligible recoveries and all 19 prior matches because 19 + 8 = 27.

## 6. Exact next steps

1. Present Albert one decision: authorize local implementation or stop. Success: no code begins
   before explicit approval.
2. If authorized, a fresh session reads the plan and starts F0. Success: first diff is tests only.
3. At the end of each phase, re-read all later phases through F6 and report drift. Success: changed
   assumptions are written into the plan or that session's own handoff before the next phase.

## 7. Constraints and gotchas

- No implementation, second gate, deploy, bake-off, DB/schema/secret change.
- Use only `responsibilityCompletionRequest(seed).sourceSpan`.
- No heading, nearby duty, prefix, alias, fixture term, weaker matcher, lower gate, higher budget, or
  model/route change.
- Merge, apply, serving stay false.
- Preserve unrelated untracked files and other handoffs.
- More than five handoffs are open. Do not delete another session's file here.

## 8. Access and environment

- Windows `al8960ofc`; PowerShell; repo `C:\repos\oracle`; branch `main`.
- `gh` is authenticated for later plan landing.
- GLM uses `ai-glm` with `AI_GLM_CALLER=codex` and an existing R2 session when available.
- Secrets remain in 1Password vault `vibe_coding`; none are needed now.

## 9. Open questions and risks

- GLM found F3 duplicated the existing late path. The plan now locks reuse of
  `lateResidualResponsibilitySeeds` and `runLateResponsibilityCompletion`; no new pass is allowed.
- GLM required a fixed object/condition boundary rule. The plan now locks it in section 8.
- GLM's final review found no P0/P1 issues and approved the plan for Albert's implementation decision.
- Row 24 is a negative control and must remain failed under this correction.
- Local replay cannot prove production readiness. A future live run needs a new owner-approved plan.
- Owner decision after review: authorize local implementation or stop.

## Handoff self-audit

Passed. Section 0 contains the only owner decision and all settled limits. Sections 1-3 identify the
app, goal, evidence, commit, push, CI, and unfinished state. Sections 4-5 preserve failures and root
causes. Section 6 gives exact gated steps through F6 and the downstream drift check. Sections 7-9
cover safety, access, and risks. A new developer can continue as effectively as this session without
this chat, and no sentence in sections 1-9 needs Albert's judgment unless it is also in section 0.
