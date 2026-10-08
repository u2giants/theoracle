---
issue: 58
status: OPEN
owner: next Oracle S03 process-owner grading session
---

# S03 real-doc acceptance — on-site grading ready (wrap-up 2026-10-08)

## 0. Decisions only the owner can make

**Blocking**
1. **Ilona + Jessica must grade the S03 bank on the site.** They have 15 items each on `/claims`. Albert must tell them to log in and Accept/Reject. Blocks plan S03 ✅ and closing #27/#58. Recommendation: send them the one-line “log in to Oracle → Claims → grade S03 items” message today.

**Already settled — do NOT re-ask**
- All data shareable with AI providers (settled earlier).
- Ilona is licensing process owner; Jessica is PM / whole POP pipeline (Albert, 2026-10-06 multi-dept bank).
- StepFun over MiMo; z.ai on hold.
- Never ask a human to approve — AI reviewers gate technical actions (2026-09-28).
- **Trigger PAT exposure: redact only, do NOT rotate** (Albert, 2026-10-06 verbatim: "redact it from the transcripts and don't rotate.").
- Vercel Production `TRIGGER_SECRET_KEY` is set to Trigger **prod** key (done this session).

**Future (not live)**
- Re-run bank against full PDF SOP chunks if graders want stronger Q9/Q10 evidence (PDFs re-ingested after bank run).

## 1. What this application is

Oracle (`u2giants/theoracle`) is POP Creations’ evidence-backed knowledge and consulting app. Parent [#24](https://github.com/u2giants/theoracle/issues/24); plan `plan_oracle_consultant_overhaul.md` (**STATUS first**). Web on Vercel `popcre/theoracle` (alias `oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`); workers Trigger `proj_wgpzsvhmsopqhvwqaycn`; app DB Supabase `eqccjfbyrywsqkxxpjvg` (Oracle’s own — **not** `popcre/shared-db`).

## 2. What this session set out to do

Resume S03 acceptance: prove Oracle understands **real** licensing/project docs, not a synthetic table. Albert’s bar: rebuild questions only from Admin → Documents production uploads; multi-dept (Ilona + Jessica); grade with process owners; tick S03 only on Accept. Then close #27/#58 and name S04 (#28).

## 3. Current verified state (2026-10-08 ~1:40 PM EDT)

- **PRs merged this session:** #77 real-doc question bank; #78 STATUS/S03-pilot run record; #79 `unpdf` PDF parse fix (workers); #80 PDF re-ingest note; #81 on-site grading tasks note. `origin/main` tip after #81: `79f1e1f`.
- **8 Admin docs** on production Supabase. Usable source: business-process.md (179 claims), Licensed Team Responsibilities (123), Pop Creations Flow PNG (78, vision), transcript (12), Licensing Sheet Automation PDF (1). 4 SOP PDFs initially failed `pdf-parse` (`__require.ensure is not a function`); fixed with `unpdf` (PR #79), workers deployed Trigger `20261006.1`, re-ingested complete (thin text-layer, 1 chunk each).
- **Question bank:** `evals/oracle2/s03-realdoc-question-bank.md` (30 Qs; L1–15 Ilona, J16–30 Jessica). Engine run on edge-dev3 `POST /api/consultant/questions`: **30/30 answered, 0 HTTP failures** (extractive pilot engine). Private answers/packets under `…/mimocode-private/oracle2/s03-realdoc-*` and `/home/ahazan/oracle-s03-evidence/`.
- **Old-logic claims wiped** (owner request): 750 claims deleted (backup `claims-backup-20261006.sql`, ~9 MB, private). **393 real-doc claims remain** (knowledge base).
- **On-site grading (product structure):** 30 `claim_review_question` gaps — Ilona 15 / 15 distinct claims, Jessica 15 / 15 distinct claims, **zero overlap**. Old non-S03 review gaps resolved. `/claims` shows only the assignee’s items. Admin `/admin/claims` sees all claims + assignees + verdicts/notes.
- **Vercel logged in** as `u2giants`. Production `TRIGGER_SECRET_KEY` = Trigger prod key (`4lm6gk2xbmmfkn3676i5kzc344` on item `scugjbpdtbwlmglhv2dmfl4chi`); sensitive, Production only. Redeployed `dpl_4FbDQert3E9DePtundxJpBj69cL8` → alias `oracle.designflow.app`. Dispatch path verified: same key triggered `document-ingestion` (HTTP 200).
- **Trigger PAT** (`ylzcsfbhmjyzjy65mnu6uxw67e`): exposure in subagent output (prefix `tr_pat_ui8whr8d…`). Full value redacted from two MiMo log files. Owner: **no rotation**. 1Password notes updated. Temp file that briefly held the full value deleted.
- **S03 is NOT accepted** until both process owners Accept. #27/#58 stay open. Do not name S04 (#28) until then.

## 4. Everything we tried that did NOT work

- Vercel device-code login via isolated Playwright browser — no session (login pages only). Fixed by opening **Chrome** for Albert and running `vercel login` until signed in.
- `vercel redeploy --yes` — invalid flag; must pass a deployment URL.
- `psycopg2` / `pg8000` unavailable in system and `MIMO_PYTHON`. Used `psql` + `1password_op_run` instead. PowerShell heredocs do not work — generate SQL to a file, then `psql -f`.
- Claim wipe SQL: successive FK failures (`extraction_candidate_evidence` has no `source_claim_id`; then `extraction_validation_results` → candidates; then `section_claims`; then `gaps.related_contradiction_id` → contradictions). Each attempt rolled back. Final script handles the full FK list from `information_schema` (see `wipe-old-logic-claims.sql`).
- Markdown review packets for Ilona/Jessica — **wrong delivery**. Albert: tasks belong on the site (`claim_review_question` / `/claims`), as done before. Packets remain private reference only.
- Combined 8-doc consultant source: large business-process.md drowned LTR retrieval. Authoritative bank run used per-doc / paired-doc sources.
- Bash tool is PowerShell here: `export`, `<<heredoc`, and bare `VAR=1` lines fail and cancel sibling tool calls.

## 5. Root causes and key findings

- `pdf-parse` + Trigger esbuild = `__require.ensure is not a function` (webpack-only). `unpdf` is the serverless-safe replacement (`apps/workers/src/trigger/document-ingestion.ts`).
- Direct Supabase host `db.eqccjfbyrywsqkxxpjvg.supabase.co` is IPv6-only from edge-dev; **session pooler** (`oracle_session_pooler` field on item `qcuyabwseaptvuzvtjejffi2ou`) works via psql.
- `document-ingestion-sweep` retries only `pending_processing`/`processing` — **failed** docs need a status reset.
- Admin → Documents writes production Supabase (`eqccjfbyrywsqkxxpjvg`), not edge-dev3 Docker Postgres (oracle2 pilot store only; volume is ephemeral — re-compose + `oracle2-bootstrap-run.py`).
- `/claims` isolation is by `gaps.target_employee_id` + `claim_review_question` + status in open/queued/asked; two gaps on the same `related_claim_ids` collapse to one claim row — S03 assignments must use **distinct claims per item** (fixed 5 collisions).
- Trigger secret key vs PAT: `tr_prod_` / `tr_dev_` trigger runs; `tr_pat_` is management (deploys, envvars). CLI `whoami` rejects good PATs — verify via `GET https://api.trigger.dev/api/v2/whoami`.
- Consultant pilot engine is extractive (quotes blocks); rarely abstains on A-category items; attaches a standing hypothetical label to every answer.

## 6. Exact next steps

1. **Albert tells Ilona and Jessica to grade** 15 items each at Oracle → `/claims` (Accept / Reject + one-line reason). You’ll know it worked when claim status/notes change and `claim_review_events` show their actions (admin can watch `/admin/claims`).
2. **Collect verdicts.** Threshold: no Fail on E/A/X; ≤1 Fail on P/H; I items label hypothesis vs fact. You’ll know it worked when both Accept (or you have a concrete Fail list).
3. **On both Accept:** update plan S03 row to ✅ with artifacts (S03-pilot.md + bank + on-site grade evidence), close #27 and #58, **then** name S04 (#28) on #24. Delete this handoff under the successor rule in the same commit if all three successor conditions hold.
4. **If any Reject:** diagnose the failed boundary (source vs retrieval vs answer) before adding features; re-run only the failed items against full PDF SOP chunks if evidence was thin.

## 7. Constraints and gotchas in force

- No production writes without assigned AI reviewer APPROVE (except small owner entries ≤10 rows). Secrets via 1Password `vibe_coding`; never print values. Sign GitHub: `Posted by MiMo chat <id> on edge-dev` (`$MIMO_SESSION_ID` may be empty → `unknown`). Worktrees; branch+PR; docs-only may merge immediately. Never rewrite root `HANDOFF.md`. Never edit another session’s `HANDOFF.d/` file.
- **Do not rotate the Trigger PAT** (owner 2026-10-06). Redaction is the chosen containment.
- Do not invent claim/answer content. Real-doc text is the only bank source.
- S03 stays open until **process-owner Accept** — not on code, not on 30/30 answers.

## 8. Access and environment

- Machine: edge-dev (Windows). SSH `edge-dev3` (Linux Docker). Repo `C:\repos\oracle` on `main`.
- Vercel CLI signed in as `u2giants`; linked `popcre/theoracle`. `.env.local` created by `vercel link` (gitignored via `.env*`).
- 1Password vault `vibe_coding`: Supabase session pooler `op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/27h4s3kiy3nta5o4u7atka4xyq`; Trigger PAT `ylzcsfbhmjyzjy65mnu6uxw67e`; Trigger secret/keys `scugjbpdtbwlmglhv2dmfl4chi` (prod key field `4lm6gk2xbmmfkn3676i5kzc344`).
- Private evidence: `C:\Users\ahazan\.local\share\mimocode-private\oracle2\` (doc text, bank answers, packets, claims backup, wipe SQL) and `/home/ahazan/oracle-s03-evidence/` on edge-dev3.
- psql / pg_dump via `1password_op_run` + env injection (values never printed).

## 9. Open questions and risks

- **Secret exposure residual:** full Trigger PAT appeared in MiMo session logs (redacted in two files) and possibly other agent transcripts not swept. Owner declined rotation — accepted residual risk (2026-10-06). Do not re-print.
- Bank run used pre-reingest PDF text-layer for Q9/Q10; full SOP chunks now exist — optional re-run.
- Extractive engine’s A-category behavior (quotes instead of abstain) is a known quality signal for graders, not a bug to fix in this workstream.
- edge-dev3 oracle2 Postgres volume disappears across days.

---

## Part (b) — sub-agent blocks

- **general-1 Vercel Trigger key:** blocked on no API token / no browser session; superseded when Albert completed Chrome device login and this session set the key.
- **general-2 confirm 8 docs / export text:** success — inventory + chunk text under `s03-doc-text/`.
- **general-3 PDF parse fix + re-ingest:** success — PR #79 `unpdf`, Trigger `20261006.1`, 5 docs complete. **Leaked Trigger PAT prefix in shell output** (handled per §0).
- **general-4 run bank + packets:** success — 30/30 via consultant Q&A; packets written; delivery later corrected to on-site gaps.

## Self-audit (handoff-writer gate)

1. Comprehensive for a new developer? Yes — product, SHAs/PRs, failed attempts, FK wipe lessons, on-site structure, exact next steps with gates.
2. As effective as this session? Yes — bank methodology, claim counts, isolation proof, Vercel/Trigger facts, owner no-rotate ruling.
3. Every relevant detail? Yes — goals, state, failures, constraints, risks, evidence paths; secrets by location only.
4. Section 0 complete? Yes — one blocking owner item (grading), settled list includes no-rotate and multi-dept owners; technical items are Blocked/findings not asks.

Posted by MiMo chat unknown on edge-dev
