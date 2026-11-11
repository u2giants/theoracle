---
issue: 474
status: OPEN
owner: mimo/ah-desktop-zh-acceptance
---

# Handoff — Chinese integration: routing bug, eval pass, and acceptance (2026-11-11)

Written 2026-11-11, 12:48 AM EST, ah-desktop, MiMo session `ses_ffe5e3c778c43ffeJNqN2nnAd4`.
Programme plan (read its STATUS table first, do not re-derive):
[plan_chinese_integration.md](https://github.com/u2giants/theoracle/blob/main/plan_chinese_integration.md).
Tracking issue: https://github.com/u2giants/theoracle/issues/474 — every item below maps to its checklist.

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Present this whole list to Albert in ONE message before starting work.

**Blocking the routing fix (§6 step 1):**
- **Who is the licensing team?** The bot routed licensing questions to Albert because its
  "most connected person" routing finds the most-mentioned name in documents (Albert is a
  lane header in the flow chart). The fix needs the actual licensing owners. **Recommendation:**
  Albert names them in one line (e.g. "Jessica Cortazar and X"), OR the next session derives
  candidates from the map evidence (the `Licensed_Team_Responsibilities` document's names) and
  Albert confirms. Blocks the routing code change only.

**Blocking the eval sign-off (§6 step 2):**
- **Approve or adjust the 10 Chinese eval questions on the site's eval page** (standing rule:
  questions are approved on the Oracle site, never as chat files). They are drafted around
  China operations incl. the sampling process per his 2026-11-10 direction. The latest run
  scored 0.38 — partly question difficulty. Albert decides whether the drafts are right for
  Ningbo's work before the acceptance pass. **Recommendation:** approve as drafted, then have
  the China reviewer flag what is wrong.

**Blocking live-proof closure (§6 steps 3–4):**
- **Who does the 10-minute Chinese Map + chat acceptance pass?** Plan suggests Emma Li
  (Ningbo office). Yuchen Zhou has already completed one round (§3). **Recommendation:** Emma
  Li, and ask her to also re-answer the two sampling questions that were dismissed (see below).
- **Emma's two sampling questions were dismissed** (probably during the post-flood cleanup of
  2026-11-10). If the sampling process is still wanted from Emma, they must be re-asked.
  **Recommendation:** re-ask them when the interview bot is switched back on (see next item).

**A standing question about the interview bot (affects every item above):**
- **The interview bot is currently OFF** (`cmap.interview_setting.enabled = false`), switched
  off deliberately — PR https://github.com/u2giants/theoracle/pull/511 says "Interview bot
  stays off". Nothing is sent while it is off. **Recommendation:** keep it off until the
  routing fix lands (that bug is why), then ask Albert before switching it on.

**Already settled — do NOT re-ask (2026-11-08/10, Albert's chat):**
- The need: "can this system understand and speak chinese (to our china employees)?" — done and deployed.
- China group (Language = 中文 in Oracle): Billy Li, David Huang, Elise Sun, Emma Li, Kelly Hu,
  Wisdom Chen, Yuchen Zhou. The DesignFlow office field is empty for everyone — the locale
  markers are the truth today.
- Review/eval questions must concern **China operations**, and the **sampling process** is
  asked specifically of Emma Li and Yuchen Zhou ("specifically ask Emma and Yuchen about the
  sampling process as well").
- The weekly question quota **stays ON** ("put the quota back on. it just sent me 30 messages
  in a row" — after a same-day removal attempt that flooded the company; see §4).
- Eval questions are approved on the Oracle site's eval page, never shuttled as chat files.

## 1. What this application is

**The Oracle** — POP Creations' evidence-backed company adviser. Employees talk to it on
Microsoft Teams and on the web; it reads company documents, diagrams and meeting transcripts,
builds a **Company Map** (how work flows across departments) and answers questions with
sources shown. Web: https://oracle.designflow.app (Vercel). Brain API:
https://oracle-brain.designflow.app (Coolify service `oracle-brain`, app uuid
`uge6pfm4qapktivto4981mtg`). Repo: https://github.com/u2giants/theoracle (**PUBLIC** — no
private data, no LAN IPs). Postgres schema `cmap` in The Oracle's own Supabase project (NOT
the shared company DB); FalkorDB graph `company`. The Chinese integration (PR #471's plan) is
implemented: language detection, CJK-safe text handling, Chinese bot/interviews/answers,
translation sidecar, cross-lingual resolution, zh-CN Map rendering, Chinese eval drafts.

## 2. What we set out to do this session, and why

Albert: "implement PR 471, adding chinese" — implement the 14-step Mandarin integration plan
([plan_chinese_integration.md](https://github.com/u2giants/theoracle/blob/main/plan_chinese_integration.md)).
Mid-session owner directives: (a) review questions must concern China operations and the
sampling process for Emma Li + Yuchen Zhou; (b) the system should initiate Teams conversations
(it can — it did); (c) remove the weekly question quota (→ flood, restored — §4); (d) wrap up.
A pre-wrap-up bug report remains open: **the bot routes licensing questions to Albert instead
of the licensing team** (the flood made the routing bias visible company-wide).

## 3. Current state — what is true right now

**Landed and deployed** (all PRs merged to `main`; brain images deployed with env pin first;
migrations `011`–`014` applied to production via `python -m brain.migrate`, run twice):
- Steps 0.1–0.4, 1.1–1.4, 2.1–2.3, 3.1, 4.1 of the plan are code-complete. See the plan's
  STATUS table for per-step evidence (each row names its tests).
- Live brain image: `ghcr.io/u2giants/theoracle-brain:76ca4e97adce2c155f84d40564b30e1340656efe`
  (the weekly-quota RESTORE, PR https://github.com/u2giants/theoracle/pull/508). `/health` green.
- The plan STATUS rows 2.1/2.2/3.1 are `🟨 code landed, awaiting live proof`; 4.2 is `⬜ open`
  with live evidence recorded in
  [docs/verification/chinese/live-proof.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/chinese/live-proof.md).

**Live-proof items (plan step 4.2) — measured on production:**
1. zh document → Map with Chinese names — **DONE** (12 Chinese mentions with verbatim quotes
   from `sample-zh-process.txt`; extraction models `scaledown/classify` + `z-ai/glm-5.3-flash`).
2. Chinese question → Chinese answer, quotes verbatim in source language — **DONE** (「我们的
   跨境审批卡在哪里？」 answered in Chinese citing English evidence in English; see live-proof.md).
3. zh employee conversation → Teams contribution source — **PENDING** (needs the acceptance
   colleague's chat; a pre-existing `Teams contribution — Yuchen Zhou — 2026-11-04` predates
   this programme).
4. zh interview question delivered → answer becomes a source — **DONE 2026-11-10** (Yuchen
   Zhou's sampling question was delivered in Chinese and answered in Chinese: "设计师会通过邮件
   告诉工厂，哪里需要改进…" — source `Interview answer — Yuchen Zhou — 2026-11-10`, id
   `7c284c28-eed7-4750-9bea-9da2e58a14e2`). NOTE: live-proof.md still says item 4 is pending —
   it predates Yuchen's answer; update it in the next docs PR (§6 step 5).
5. zh eval run — run `45e2d569-b1fe-47e5-9e84-b6ff63fb79ee` (2026-11-10, 15 questions incl.
   10 zh China-ops drafts) — mean **0.3778**, below the plan's 0.6 target. The earlier
   fixture-replay calibration run `25914471-8521-4d21-b465-d1540a154292` scored 1.000.

**Current production switches:**
- Interview bot: **OFF** (`cmap.interview_setting.enabled = false`) — deliberate, per PR #511
  ("Interview bot stays off"). Do not switch on without asking Albert (§0).
- Weekly quota: **ON** (2 per person per week) — restored 2026-11-10 after the flood; this is
  a standing rule now.
- The 10 zh China-ops eval questions are on the site's question list (awaiting Albert's
  approval on the eval page). Emma Li's 2 sampling questions are `dismissed`; Yuchen Zhou's is
  `answered` (see above).

**The routing bug (open):** licensing-domain questions auto-route to Albert Hazan. Evidence:
the 2026-11-10 flood delivered him 52 messages (Jennifer Chaffier 205, Jessica Cortazar 129);
questions like "Who is the final approver for a complete…", "What is the formal hand-off
process…" targeted him via `select_target`'s most-connected-Person rule. The Pop Creations
flow chart names "Albert :)" as a lane header, so the Person entity "Albert" accumulates the
largest edge weight to almost every process entity and wins every routing contest. The
investigation query (never executed — wrap-up froze work) is reproduced in §6 step 1.

**Not committed / not started:** nothing of this session's is unpushed. The routing fix, eval
question sign-off, and acceptance are not started (this handoff's job).

## 4. Everything we tried that did NOT work

1. **Removing the weekly question quota (2026-11-10, PR #507).** Owner asked; implemented,
   tested, deployed. Within one tick the uncapped loop sent EVERY open question in one pass:
   ~1,700 messages in two hours company-wide (205 to Jennifer Chaffier, 52 to Albert).
   Owner: "put the quota back on. it just sent me 30 messages in a row". Restored in PR #508
   (revert), deployed, flood counter rows backed up to
   `cmap.interview_send_flood_backup_20261110` and cleared so the restored quota would not
   lock everyone out for 7 days. **Lesson: the quota is load-bearing; never remove it. The
   tick's per-question loop assumes a cap exists.**
2. **`ai-pr-wait` (the bounded CI waiter).** Repeatedly timed out or reported
   "checks=SUCCESS / still in progress" and twice failed with internal tool errors
   ("reclaiming abandoned lock", "request exceeded the 30s API limit"). Workaround that
   worked: `gh pr view --json mergeStateStatus` + `gh pr checks` directly after a fixed sleep.
3. **STATUS-table merge conflicts on almost every PR.** Each step's PR edited the plan's
   STATUS table; adjacent-row edits conflicted when the previous step's squash merged. Every
   rebase needed a hand-resolution of the same table. If you land more steps: rebase onto
   `origin/main` immediately before merge and keep BOTH rows' new content.
4. **Windows PowerShell has no heredoc** (`<<'EOF'` is a parser error) — every `gh`/`git -m`
   multi-line call failed once; fix is a message file + `--body-file`/`-F`.
5. **Windows argv loses CJK**: `curl -d '{"question": "我们的…"}'` sent question marks only —
   the production answer said "The question came through as only question marks". Fix:
   write the JSON body to a UTF-8 file and use `--data-binary @file`. Same class of bug as
   the cp1252 console (`print` of Chinese raised `UnicodeEncodeError`); fix:
   `sys.stdout.reconfigure(encoding="utf-8")`.
6. **`git commit -m "…\"quote\"…"` through PowerShell** mangles quotes and half-parses; use
   `git commit -F <file>`.
7. **zh eval drafts vs the fixture test corpus.** The first re-cut of zh questions pointed at
   production sources (`business-process.md` etc.); `test_eval_fixture.py` asserts every
   question's expected sources are cited by the FIXTURE corpus, which cannot cite production
   sources. Fixed by scoping that assertion to the five fixture questions (the zh set is
   proven by the live run) — see
   [test_eval_fixture.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_eval_fixture.py).
8. **First live zh ask was in English.** The prompt changes were live but the request body was
   mangled (item 5 above); re-sent from a UTF-8 file and got a full Chinese answer.

## 5. Root causes and key findings

- **Routing bias root cause:** `select_target` in
  [interview/tick.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/tick.py)
  maps the question's entity_ids to Person entities by summed edge weight
  (`_PERSON_WEIGHT_SQL`) and picks the most connected person reachable. Any frequently-appearing
  name (flow-chart lane headers like "Albert :)") wins against the domain expert. This is the
  licensing-questions-to-Albert bug's mechanism.
- **The weekly quota is a flood guard**, not a courtesy: the tick loop sends one message per
  open question per pass with no per-pass bound (§4 item 1).
- **China group = `public.employees.locale = 'zh-CN'`** — 7 people (§0). The DesignFlow
  directory's `office_location` is EMPTY for all 59 rows (`api.oracle_user_directory()`, read
  via the sanctioned read-only login `oracle_directory_reader`); locale markers are the only
  China-office signal in the data.
- **Cross-lingual answers work live**: a Chinese question produced a Chinese answer that
  quoted English evidence in English and refused to guess (live-proof.md item 2).
- **`cmap.entity_alias` predates this programme** (001 schema) — the plan's claim "no alias
  table" was stale; migration `012` adds `lang`/`source` to the existing table instead.
- **ScaleDown extracts Chinese names verbatim** (measured 8/8 on the fixture; STATUS row 1.1) —
  no zh→frontier routing needed.
- **Interview sends open the Teams 1:1 chat themselves** (no prior employee message needed) —
  that is how Emma/Yuchen were asked; `_post_proactive` → web `api/teams/bot/proactive`.
- **PR #511 (another session, Claude on edge-dev3, merged 2026-11-11)** changed question
  generation ("questions come only from what the brain does not know") and left the interview
  bot OFF. It also dismissed most flood-era questions. Coordinate before re-enabling the bot.

## 6. Exact next steps

1. **Fix the routing bug (top priority).** First ask Albert §0's licensing-team question (one
   message with the whole §0 list). Then: inspect what the map knows — run the never-executed
   investigation: query `cmap.open_question` rows with `target_employee_id` = Albert's id
   (`3a225fe6-4b4f-49a9-9896-41ec9fb4294c`… verify by name), and the Person entities with the
   highest edge weight to licensing entities. Implement the fix in `select_target`
   ([tick.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/tick.py)):
   prefer people who **contributed evidence about the question's entities** (their own Teams
   contributions / interview sources mention those entities) over raw connectivity; keep
   manual `target_employee_id` first (unchanged). Tests: extend
   [test_interview.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_interview.py)
   with a case where a famous-but-uninvolved person loses to the contributor. PR → merge →
   deploy (env pin first — see §7). You'll know it worked when a licensing question with
   candidates {Albert, licensing contributor} routes to the contributor in the unit test and
   the tick no longer targets Albert for licensing entities.
2. **Eval sign-off + mean.** Put the §0 question to Albert; on the site's eval page he
   approves/edits the 10 zh China-ops questions. Then rerun `POST /eval/run` and record the new
   run id + mean in the plan STATUS row 4.2. You'll know it worked when a run after approval
   scores ≥ 0.6 (the plan's artifact-5 gate) or Albert explicitly accepts a lower mean.
3. **Acceptance pass + item 3.** With the interview bot still off until step 1 lands and
   Albert approves re-enabling: the chosen China colleague (§0) spends 10 minutes on the Map
   and a Chinese chat; the chat's contribution becomes a Teams contribution source (live-proof
   item 3) and the colleague marks what is wrong (business acceptance).
4. **Re-ask Emma's dismissed sampling questions** (§0) once the bot is re-enabled — they were
   dismissed 2026-11-10 and the sampling process is still wanted.
5. **Docs PR:** update
   [live-proof.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/chinese/live-proof.md)
   item 4 to DONE (Yuchen's answer source `7c284c28-eed7-4750-9bea-9da2e58a14e2`), record run
   `45e2d569-b1fe-47e5-9e84-b6ff63fb79ee` mean 0.3778 under item 5, and mark rows 2.1/2.2/3.1
   in the plan STATUS `✅` only after their live-proof touches (2.1/2.2 need one live bot/answer
   moment in the acceptance pass; 3.1 needs one zh-locale Map screenshot from the live site —
   the e2e screenshots `12-zh-community.png`/`13-zh-entity.png` exist but the live-site
   screenshot is the plan's wording). You'll know it worked when `gh issue view 474`'s
   checklist and the plan STATUS agree and `- [ ] live proof` can be checked.

## 7. Constraints and gotchas in force

- **Repo is PUBLIC.** No private data, employee content, real transcripts, LAN IPs in commits.
  Test fixtures are synthetic (`docs/verification/chinese/fixtures/`).
- **Branch policy:** never push to `main`. Branch, PR, let checks decide; merge with
  `gh pr merge --squash` (prose-only PRs: `bin/ai-doc-safety` then `--admin`). Sign GitHub
  content `Posted by MiMo chat <id> on <machine>`.
- **Quotes are evidence** (plan L2): never translate or normalize a quote; test it byte-for-byte.
- **One brain** (L1): no separate Chinese map. **English UI chrome** (L3). **Names stay
  source-language** (L4/L6: English canonical in columns, zh in `cmap.translation`).
- **Migrations:** `cmap` migrations are `apps/brain/brain/sql/NNN_*.sql` + `python -m brain.migrate`
  run MANUALLY against production (deploys never migrate). `cmap` is NOT the shared DB —
  never route these through `popcre/shared-db`.
- **Brain deploys:** `brain-image.yml` publishes `ghcr.io/u2giants/theoracle-brain:<full main sha>`;
  Coolify PATCHes env `BRAIN_IMAGE_TAG` to that sha BEFORE `POST /api/v1/deploy?uuid=…` (the
  stale-pin rule — a deploy with an old pin silently runs old code). Never redeploy while
  `cmap.job` has running/queued rows. Coolify API `http://hetz:8000/api/v1` over the tailnet.
- **The weekly quota stays ON** (owner ruling 2026-11-10 after the flood). Do not remove it.
- **The interview bot stays OFF** until the routing fix lands and Albert approves re-enabling
  (PR #511's wording + §0).
- **ui-task gates:** `ai-task-gates start --class code|deployment` per work type;
  `check --before deploy --acknowledge "<Albert's exact words>"` for deploys.

## 8. Access and environment

- Machines: ah-desktop (Windows, this session) and edge-dev3 (Linux). Canonical checkout
  `D:\repos\oracle\theoracle` is landing-only; this session worked in worktree
  `D:\repos\oracle-worktrees\zh-integration` (machine-local environment fact — the successor
  may make its own worktree).
- `gh` authenticated as `u2giants`. Commit identity `Albert Hazan <u2giants@users.noreply.github.com>`.
- 1Password vault `vibe_coding` (values ONLY via `1password_op_run` + `op://` refs — never
  print): "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, …)" field
  `oracle_session_pooler` (prod DB); "Oracle Brain shared token - The Oracle
  (BRAIN_SHARED_TOKEN)" field `BRAIN_SHARED_TOKEN`; "Coolify API token - Oracle deploy -
  release sessions only (theoracle)" field `credential`; "OpenRouter API Key - The Oracle
  (local .env.local)" field `OPENROUTER_API_KEY`; "Supabase DB login oracle_directory_reader -
  shared POP database (production, read-only)" field `password` (directory reads only —
  `api.oracle_user_directory()`).
- Production URLs: web https://oracle.designflow.app, brain https://oracle-brain.designflow.app
  (`/health` free; everything else needs `x-brain-token` + `x-user-id` headers, user id = an
  admin's `employee_identities.auth_user_id`).
- Brain model seats (production, via `GET /models`): flat fallback `z-ai/glm-5.3-flash`, embed
  `voyageai/voyage-4-lite`.
- Local test DB for brain pytest: any scratch Postgres (pgvector) + FalkorDB; this session used
  containers `zh-brain-pg`/`zh-brain-fk` on edge-dev3 (ports 5433/6380) — recreate if gone:
  `docker run pgvector/pgvector:pg16` etc. Never point tests at production (`_clean_cmap`
  truncates).

## 9. Open questions and risks

- **Routing design (risk: wrong fix).** Raw connectivity is wrong; evidence-ownership
  weighting (§6 step 1) is the proposed fix but has not been validated against real data —
  the first session should look at actual Person-entity weights before committing to it.
  Coordinate with PR #511's author work (question generation) so the two changes do not clash.
- **Eval mean 0.3778 < 0.6** (run `45e2d569…`). Could be question difficulty, corpus gaps, or
  the grader; the plan's artifact-5 gate is 0.6. Albert's question approval (§0) is step one;
  if the mean stays low after approval, record the accepted mean in STATUS with his words.
- **Flood-era residue:** `cmap.interview_send_flood_backup_20261110` holds the 1,704 flood rows
  (kept for recovery). Decide later whether to drop it; not urgent.
- **Dismissed sampling questions** (Emma ×2) — if the sampling process is still wanted they
  must be re-created; the content is in §3/§6 step 4.
- **Mixed-language employees** (plan O1): the thread-language pin exists (step 2.1) but has
  no live proof yet; if the acceptance pass shows confusion, the pin rule is the first knob.
- **PR #511 interplay:** another session owns question generation and left the bot off; treat
  that as deliberate and coordinate before re-enabling.
