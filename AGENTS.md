# AGENTS.md — The Oracle Developer Guide

Read this first. It is the canonical operating guide for developers and AI coding sessions working in `C:\repos\oracle`.

## 1. Project summary

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations / Spruce Line. Employees interact with it through chat and document uploads; workers extract operational claims with quote-level evidence; deterministic validators gate promotion into approved claims; synthesis workers maintain traceable Brain sections; admin screens review runs, caches, claims, gaps, contradictions, and taxonomy proposals. The outcome that matters is explainable business knowledge: every important answer or synthesis artifact must be traceable back to messages, document chunks, or approved claims.

## 2. Multi-model AI note

There is no universal ignore-file standard across AI coding tools.

`.claudeignore` works for Claude Code.

When using any other AI tool, paste this file as your first message and follow the instructions in the "What to ignore" section.

## 3. Task router — where each section now lives

`AGENTS.md` is kept small because it loads into every AI session. The full text of
sections §3, §4, §7–§9 and §11–§15 moved **verbatim** (same headings and numbers)
into `docs/agents/`. Every rule there still binds exactly as before; any reference
to "AGENTS.md §N" means the file below. Read only the file(s) your task needs.

| Section | File | Read it when |
|---|---|---|
| §3 Documentation map (full task → docs table and its rules) | `docs/agents/03-documentation-map.md` | Choosing which topic doc, plan, or handoff to read for a task; adding, removing, or renaming docs (the map must be updated) |
| §4 Repository structure | `docs/agents/04-repository-structure.md` | Finding where code, docs, plans, or scripts live |
| §7 Task-to-file navigation | `docs/agents/07-task-to-file-navigation.md` | Deciding which files to edit for a common change (workers, Teams/Recall, UI, APIs) |
| §8 Data model and external identifiers | `docs/agents/08-data-model-and-external-identifiers.md` | Schema, migrations, external IDs, data flow |
| §9 Container and service inventory | `docs/agents/09-container-and-service-inventory.md` | Which services/projects exist and where they run |
| §11 Intentional quirks and non-obvious decisions | `docs/agents/11-intentional-quirks.md` | **Before changing any behavior** that looks odd — model routing, providers, retrieval, extraction, quotes, migrations, MCP, Teams, caches, China layer |
| §12 Credentials and environment | `docs/agents/12-credentials-and-environment.md` | Env vars, secrets, 1Password, local `.env.local`, production database access |
| §13 Deployment, incl. **Release & CI/CD policy** | `docs/agents/13-deployment.md` | **Before any commit, push, branch/PR decision, deploy, worker deploy, or migration** — it holds the binding branch model, release path, and migration-path rules |
| §14 Critical incidents | `docs/agents/14-critical-incidents.md` | Investigating a bug/incident; touching providers, migrations, Drizzle journal, batch, webhooks, Trigger.dev environments, or Entra secrets |
| §15 Pending work | `docs/agents/15-pending-work.md` | Continuing unfinished work, choosing what to do next, or updating status |

Always-read rules that stay in this file: §1, §2, the five-minute orientation, task
declaration, §3a handoffs, §5 Prime Directive, §6, §10 ignore rules, and the host/server
boundary at the end.

## Five-minute orientation

If you are new to this repo, read only this path first:

1. `README.md` for the repo shape.
2. This file through §10 for operating rules, what to touch, external IDs, services, and ignore rules (§4 and §7–§9 are in the `docs/agents/` files named in §3).
3. The files in `HANDOFF.d/`, newest first (`HANDOFF.md` is only a pointer to that folder).
4. The single topic doc named by the §3 documentation map (`docs/agents/03-documentation-map.md`).

Do not open every Markdown file. Most tasks need `AGENTS.md` plus one topic doc and the affected source files.

## Task declaration

Before changing files, run `ai-task-gates start --class <class>`. Before a
protected action, use `ai-task-gates check --before <action>`. The repository
declaration keeps rulebooks, managed-platform release files, and the canonical
Oracle migration path under their existing stronger controls; it does not
replace the workflow, migration, review, or owner-authorization rules below.
The command is installed by the public `popcre/ai-devops` recovery toolkit. If
it is unavailable, restore that toolkit from its `docs/restore-from-zero.md`
procedure before editing this repository.

## 3a. Handoffs — `HANDOFF.d/` and the successor rule

Handoffs live as one write-once file per session under `HANDOFF.d/`, named
`<UTC-timestamp>-<machine>-<agent>-<slug>.md`. Root `HANDOFF.md` is a static
pointer and is never rewritten. The full standard is
`templates/system/handoff-standard.md` in `u2giants/ai-devops`.

**A file's presence means the workstream is OPEN.** That only stays true if
finished files are removed, so removal is part of the work, not paperwork:

- **Write:** each session creates exactly ONE new file. Never edit or delete
  another session's file for any reason other than the successor rule below.
- **Successor rule (this is what stops the pile-up).** The session that finishes
  the NEXT step of a workstream deletes the PREVIOUS step's file, in the same
  commit that finishes that step. A session almost never retires its own file,
  because it writes the handoff precisely when the work continues past it.
  Delete only when all three hold, and say so in the closing report:
  1. the predecessor's status line says its work was committed and pushed, and
     you verified those commits are on `main`;
  2. every still-open obligation it names is carried forward — into the plan's
     STATUS table or drift log, or into YOUR new file;
  3. nothing in it is a decision or dead end recorded nowhere else.

  If any one fails, keep the file and say which one failed. Git history preserves
  every deleted handoff, so nothing is ever lost.
- **Multi-phase plans are the trap.** A plan executed as P0…P8 or F0…F6 produces
  one handoff per phase. Without the successor rule that is nine open files for
  ONE workstream. The plan document is the durable record; the handoff is only
  the baton. Retire the baton you just took.
- **Standing exception — the legacy archive.**
  `HANDOFF.d/2026-08-06T1510Z-t16-codex-legacy-migrated-handoff.md` (~185 KB) is NOT a session
  baton and no successor session will ever retire it. It is pre-2026-08-06 history, and it is kept
  for exactly one reason: it holds the only full text of the open `GAP-1`…`GAP-14` and
  `REL-1`…`REL-9` register. **The moment that register is moved into a real plan document with a
  STATUS table, delete this archive file in the same commit that lands the plan.** Git history
  keeps it. Do not leave both — a duplicated register is how a stale copy silently wins. Until then
  it stays, and it does not count toward the threshold below.
- **Threshold:** more than 5 files in `HANDOFF.d/` is a defect. Say so loudly at
  session start, list them oldest-first, and retire the ones the successor rule
  clears before starting new work.

## 5. Prime Directive: custom-code boundary

Our custom code lives here:

- `apps/web/app/**`
- `apps/web/lib/**`
- `apps/workers/src/**`
- `packages/**`
- `docs/**`
- `.github/workflows/**`
- root project docs/config files such as `README.md`, `AGENTS.md`, `CLAUDE.md`, `.env.example`, `vercel.json`, `turbo.json`

Everything else requires justification before touching.

Specific boundaries:

- Do not edit `node_modules/`.
- Do not hand-edit generated Drizzle files under `packages/db/migrations/0*.sql`.
- Do not scatter project logic into `apps/web/components/ui/*`; extend behavior from app-owned files instead.
- Do not change `oracle_master_spec.md` casually; if code and spec conflict, record the conflict in `DECISIONS.md`.

## 6. Core modification inventory

| File | Change made | Why it was necessary | Risk during upgrades |
|---|---|---|---|
| _(none)_ | — | No framework/vendor files are intentionally patched in this repo. | — |

## 10. What to ignore

Do not load these into AI context unless a task explicitly requires them:

- `node_modules/`
- `apps/web/.next/`
- `out/`
- `build/`
- `dist/`
- `.turbo/`
- `.vercel/`
- `.trigger/`
- `supabase/.temp/`
- `.cache/`
- `coverage/`
- `.claude/`
- `.playwright-mcp/`
- `packages/ai/evals/runs/`
- `pnpm-lock.yaml` unless dependency resolution itself is the task
- `packages/db/migrations/0*.sql`
- `packages/db/migrations/meta/`
- `.env.local`
- `oracle_master_spec.md` unless product/spec alignment is the task
- `oracle_ai_architecture_prompt caching.md` unless AI architecture or prompt-cache retrofit history is the task
- `china_imp.md` unless the task is the China bilingual claim layer / claim translation / recertification
- `docs/oracle/` unless the task touches the AI-retrofit spec directly

For orientation, follow the documentation map near the top of this file. Do not load broad source files such as `packages/db/src/schema.ts` or `packages/ai/src/providers/*.ts` unless the task needs that subsystem.

## Host / server changes — do NOT make them here

The `hetz` server's host/OS layer is managed by **Ansible** in **[`u2giants/ansible`](https://github.com/u2giants/ansible)**.
To change the server (packages, users, firewall, DNS, Docker *engine* config, system cron,
systemd units, Cloudflare Tunnel 1, the backup watchdog), **open a PR there** and let CI apply
it — **never** SSH into the box and hand-edit it. Manual changes are drift and get reverted by
the next apply. See [`u2giants/ansible/AGENTS.md`](https://github.com/u2giants/ansible/blob/main/AGENTS.md).

This repo is **not** the host layer. Its own changes belong here and deploy through their normal
pipeline (e.g. Coolify). Don't put host-level changes here, and don't manage this service's
container with Ansible. Scope boundary: **Ansible owns the host; Coolify owns the apps.**
