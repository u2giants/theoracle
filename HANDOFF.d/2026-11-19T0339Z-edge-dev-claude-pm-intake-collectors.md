---
issue: 607
status: OPEN
owner: claude/intake-handoff
---

# Handoff — PM message intake: readers built, cleaning next (2026-11-18)

Tracking issue [u2giants/theoracle#607](https://github.com/u2giants/theoracle/issues/607); parent [#520](https://github.com/u2giants/theoracle/issues/520). The plan is the brief: [plan_pm_message_intake.md](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) — read its STATUS table first, then the lead launch prompt. Do not re-plan.

## 0. Business decisions only the owner can make

None open. Already settled — do NOT re-ask:
- Read the two project managers' mailboxes, Teams chats (private and group) and company ClickUp; 90-day window after a two-week pilot; do not announce it to them; ScaleDown first, then only gpt-6-luna, claude-haiku-5.5, glm-5.3-flash or deepseek-4.1-flash, no frontier model (owner, 2026-11-18).
- Mail.Read is granted to ALL mailboxes, not just two — the owner did it himself on 2026-11-18 because the system will expand to everyone. Do not add a two-mailbox restriction.
- The Graph app ("dflow alerts") is shared with DesignFlow alerts; owner said sharing is fine (2026-11-18).

## 1. What this application is

The Oracle (repo u2giants/theoracle, public) builds a company map of POP Creations from meetings, documents and now messages. The Python "brain" service in apps/brain reads sources, stores them in Supabase Postgres schema `cmap`, and extracts facts with small models. This workstream adds the two project managers' ClickUp, Teams chats and email as sources.

## 2. Goal of this session

Do plan steps 0.1 (size and cost forecast before any paid call), 1.1 (staging tables), 1.2 (ClickUp reader), 1.3 (Teams chat reader), and unblock email (5.1).

## 3. Current state (all merged to main)

- 0.1 done: [brain/intake/sizing.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/sizing.py). 90-day forecast on #607 (comment 6993848642): 1,045 passages, $0.12–$0.80 total across candidates. Teams is ~97% of volume. PR #617.
- 1.1 done: [sql/036_message_intake.sql](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/036_message_intake.sql) (`cmap.intake_item`, `cmap.intake_thread`, `cmap.source.origin/external_ref`). Spend cap: `intake_spend_cap()` in [config.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/config.py) refuses to run unless `BRAIN_INTAKE_MAX_USD` is set.
- 1.2 done: [brain/intake/clickup.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/clickup.py), PR #620. Live dry run: 160 items = 160 in sizing.
- 1.3 done: [brain/intake/graph_chats.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/graph_chats.py) plus shared Graph client [brain/graph_ms.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/graph_ms.py), PR #622. Live dry run: 12,864 kept vs 12,828 (0.3%), 956 threads vs 954.
- Email access proven: mailbox read 200 for both (#607 comment 6998806988). 5.1 is open, unblocked.
- Not started: 1.4 onward, 5.1. No real data has been written to the tables yet (only dry runs).

## 4. What did NOT work

- Matching ClickUp members by email: ClickUp emails differ from the directory. Fixed: full name, then unique first name.
- Using the project-manager job title to find people: one manager's directory title is not a project-manager title. Title only breaks ties now.
- Only assigned ClickUp tasks: just 10. Now assignee, watcher, creator or commenter.
- ClickUp comments fetch returned only 25 newest; now paged with start/start_id (`task_comments` in sizing.py).
- Failing on a Graph 403: one meeting chat refuses; now skipped and counted.
- Failing on repeated ids in Graph chat paging: live paging repeats ~5 messages in 90 days; now skipped and counted (`PAGING_DUPLICATES` in graph_ms.py).
- Direct Supabase host does not resolve over IPv4: use the session pooler field.
- The 1Password MCP op_run tool dropped its connection on long runs: use `op run --env-file` in Bash.

## 5. Key findings

- Graph app-only token works for chats and now mail; app is "dflow alerts", tenant popcre.com.
- Free cleaning in sizing drops only 2–9% of tokens, so the plan's 1.5 gate (build only if it would drop ≥30%) likely ends "not needed" — run its 200-thread probe to decide.
- Tests needing Postgres run only in CI (no Docker on edge-dev); pure-logic tests can be run directly by importing test modules.

## 6. Exact next steps

1. Step 1.4 (lead-only): write apps/brain/brain/intake/clean.py per the plan, drop-only. Done when tests/test_intake_clean.py proves every kept line is a byte-identical substring of the input and CI is green.
2. Step 5.1 email reader, built like graph_chats.py using graph_ms.py, threads by conversationId. Done when a live dry run prints counts and synthetic tests pass in CI. (Re-run sizing afterward to add email to the forecast and post it on #607 before any paid call.)
3. Steps 1.5, 1.6, then 2.1–2.5, 3.1, 4.1 in plan order. Every paid run must pass `intake_spend_cap`.
4. Update the STATUS table in every PR. At the end of each phase, re-read all downstream phases to plan-end and record any drift in STATUS.
5. When a later step finishes, delete this file (successor rule).

## 7. Constraints

- Repo is public: no message content, names, ids, emails or addresses in git, issues, PRs or logs. Counts and dollars only.
- No paid model call before its forecast is on #607; hard spend cap each run.
- Branch and PR; the AI merges its own PRs; reviews are advisory. Sign GitHub posts. Times in EST.
- Never commit $TMPDIR files.

## 8. Access

- Secrets in 1Password vault vibe_coding: Supabase item field `oracle_session_pooler` for DATABASE_URL; ClickUp item field "api token"; Graph client secret for "dflow alerts". Build an op:// env file under $TMPDIR and run with `op run --env-file`.
- Azure CLI is signed in on edge-dev as a global admin, but the AI does not change tenant security settings itself.
- gh authenticated as u2giants.

## 9. Risks

- Mail.Read is tenant-wide: the readers must only ever query the named people. Keep resolve_people strict (exactly one active match).
- Email volume is unknown until sized; it may change the forecast materially.

Self-audit: §0 sweep run (owner items all settled); dead ends §4; gates §6; references are GitHub URLs; status explicit §3.
