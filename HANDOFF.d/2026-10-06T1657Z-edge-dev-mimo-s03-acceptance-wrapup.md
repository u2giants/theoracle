---
issue: 58
status: OPEN
owner: next Oracle S03 acceptance session
---

# S03 acceptance / upload+ingestion — wrap-up 2026-10-06

## 0. Decisions only the owner can make

**None blocking.** Settled (do not re-ask): all data shareable with AI providers; Ilona is licensing process owner; StepFun over MiMo; z.ai on hold; never ask a human to approve — AI reviewers gate technical actions.

Future owner items (not live):
1. **Vercel `TRIGGER_SECRET_KEY`** — if a human must create a Vercel API token (no CLI login on edge-dev). Otherwise AI sets `tr_prod_…` once it has a token. Blocks self-dispatch of document ingestion; sweep + manual kicks still work.
2. **Ilona + Jessica process-owner grading** of the 24-question bank against **uploaded production docs** (not the 3-row synthetic table). Blocks S03 ✅.

## 1. What this application is

Oracle (`u2giants/theoracle`) is POP Creations’ evidence-backed knowledge and consulting app. Parent [#24](https://github.com/u2giants/theoracle/issues/24); plan `plan_oracle_consultant_overhaul.md` (STATUS first). Web on Vercel `prj_rP6Jlima7iK1paffEPhLqxlswGsC`; workers Trigger `proj_wgpzsvhmsopqhvwqaycn`; app DB Supabase `eqccjfbyrywsqkxxpjvg` (Oracle’s own — not `popcre/shared-db`).

## 2. What this session set out to do

Finish S03 acceptance (real-data journey + Ilona review), then (after Albert’s direction) use real uploaded docs and a large question set — not three fact checks.

## 3. Current verified state (2026-10-06 ~1:00 PM EDT)

- **Merged to main:** PRs #60–#75 (store-backed pilot, jsonb fix, S03-pilot.md, Ilona outcome, question bank, admin upload one-file-at-a-time). Tip after wrap-up docs: see `origin/main`.
- **Muse plan-review APPROVE** on `54b6284` (recorded on #58). Codex often at capacity; Grok cancels; DeepSeek flaky.
- **Real-data journey** on **edge-dev3** (Docker `oracle2-s02-postgres-1`, 127.0.0.1:55432): Playwright 6/6; connection `2→3`; 4 then 3 citations. Ilona (via Albert) **2 Accept / 1 Reject** — email notices omitted from “usually no formal notice”. v2 re-run includes email notices.
- **24-question bank** (`evals/oracle2/s03-licensing-question-bank.md`) ran on a **3-row table** — 23 answers / 1 abstention; **12/13 table-silent questions still quoted** the table (weak understanding signal). Albert: questions must come from real docs; use Oracle in-app Q&A for process owners.
- **8 real docs uploaded** via Admin (SOPs artwork/packaging/mockup, Licensing Sheet Automation, Licensed Team Responsibilities, business-process.md, Pop Creations Flow PNG, transcript). Immediate Trigger dispatch failed → **manually triggered all 8** (HTTP 200) on 2026-10-06. Status was `pending_processing`.
- **Admin multi-file upload** was broken (one multipart body → `Request Entity Too Large` / JSON parse). Fixed: sequential per-file POSTs + clear 413 (PRs #73–#75).
- **Vercel `TRIGGER_SECRET_KEY` not set / not prod** — web cannot `tasks.trigger()`. Sweep `document-ingestion-sweep` cron `30 */4 * * *` recovers. Blocked: no Vercel CLI login (“you do not have access”).
- edge-dev3 Postgres **volume disappears across days** — re-`compose up` + `bootstrap_pilot_authority` (key at `/home/ahazan/oracle2-owner-ed25519.pem`; vault note “Oracle2 pilot owner keypair”).

## 4. Everything we tried that did NOT work

- Local scoop Postgres on edge-dev (autovacuum crash); Docker Desktop winget (UAC exit 4294967291); WSL staged but needs reboot (`docker-s03-continue.ps1`).
- Codex plan-review: many REJECT cycles then “model at capacity”; Grok door `cancelled`; DeepSeek provider call failed.
- Multi-file admin upload single FormData → 413 non-JSON.
- `asJson` double-encoded jsonb → 500 on questions (fixed `sql.json` / `parseJson`).
- Invented 3-row process table + 24 questions **not grounded in ingested docs** (Albert rejected that methodology).

## 5. Root causes and key findings

- Platform request body limit (~4.5MB) vs one-request multi-file upload.
- Trigger dispatch depends on **prod** `TRIGGER_SECRET_KEY` on Vercel (incident 2026-06-04: dev key silently drops work).
- Thin pilot retrieval is keyword-overlap; almost never abstains on short tables — not proof of complex-topic understanding.
- Answer builder quotes process-table rows verbatim — **source table wording is the control point** for fact correctness.

## 6. Exact next steps

1. **Vercel Trigger key:** obtain Vercel access (`vercel login` or token), set Production `TRIGGER_SECRET_KEY` to Trigger **prod** key (`tr_prod_…` from 1Password item `scugjbpdtbwlmglhv2dmfl4chi` field “Production API key”), redeploy/verify `vercel env ls production`. Gate: new Admin upload shows no “Immediate ingestion dispatch failed”.
2. **Confirm the 8 docs ingested** (Admin → Documents; claims/chunks present).
3. **Rebuild question bank from those uploaded docs** (Ilona + Jessica departments). Prefer Oracle’s in-app process-owner Q&A as Albert directed. Grade with Ilona (and Jessica if multi-dept). Gate: S03-pilot.md + plan S03 row ✅ only on process-owner accept of understanding — then close #27/#58, name S04.

## 7. Constraints and gotchas in force

- No production writes without assigned AI reviewer APPROVE (except small owner entries rule). No employee messages / public meetings for S03 proof. Secrets via 1Password `vibe_coding`; never print values. Sign GitHub: `Posted by MiMo chat <id> on edge-dev`. Worktrees; branch+PR; docs-only may admin-merge. Never rewrite root `HANDOFF.md`.

## 8. Access and environment

- edge-dev Windows; edge-dev3 Linux SSH `edge-dev3` (Docker). Oracle DB creds via Trigger prod envvars / 1Password. Trigger PAT: `ylzcsfbhmjyzjy65mnu6uxw67e` field id `qeqqkatqor6dphspzwyandzwhe`. Vercel CLI **not** logged in on edge-dev. Private evidence: `C:\Users\ahazan\.local\share\mimocode-private\oracle2\` and `/home/ahazan/oracle-s03-evidence/` (edge-dev3).

## 9. Open questions and risks

- **Secret exposure:** Trigger prod envvars (model keys, DB URLs) were printed into tool output during diagnosis — treat transcript as sensitive; rotation optional/owner. Do not re-print.
- In-app Q&A / interview path for process owners not yet wired for S03 grading (Albert wants that product function).
- Question-bank runs used a thin table; do not treat 23/24 answers as quality proof.

---

## Part (b) — sub-agent blocks

- **general-1 Docker on edge-dev:** blocked UAC/reboot; staged WSL; scoop docker CLI only.
- **general-2 edge-dev3 store:** success — compose postgres, schema, bootstrap `…0003`.
- **general-3 first journey:** success — Playwright 6/6; jsonb bug found; evidence on edge-dev3.
- **general-4 v2 journey (email notices):** success — answer includes periodic licensor email.
- **general-5 24 questions:** success mechanically; weak abstention quality.

## Self-audit (handoff-writer gate)

1. Comprehensive for a new developer? Yes — product, SHAs/PRs, failed attempts, exact next steps, gates.
2. As effective as this session? Yes — Ilona verdict, upload 413 fix, Trigger key gap, question-bank method warning.
3. Every relevant detail? Yes — goals, state, failures, constraints, risks, evidence paths; no secret values.
4. Section 0 complete? Yes — owner items scoped; technical approvals to AI reviewers.

Posted by MiMo chat $env:MIMO_SESSION_ID on edge-dev
