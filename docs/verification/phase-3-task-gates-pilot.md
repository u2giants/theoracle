# Phase 3 task-gate pilot — `u2giants/theoracle`

## Scope and routing measurement

Measured from `origin/main` at `53ca432bf594` on 2026-09-09. The pilot adds one
short route and does not trim or replace existing instructions.

| Surface | Before | After | Headings | SHA-256 |
|---|---:|---:|---:|---|
| `AGENTS.md` | 142,706 bytes / 1,361 lines | 143,517 bytes / 1,373 lines | 77 before / 78 after | before `91b434dc0104c2ddd2ebd824e9c53057376a9ed577f59a76304ee3ae3e041388`; after `01a711411d67f421a072d646f2751ec0deba911084bc65ae14d7d63bf6cfebca` |
| `CLAUDE.md` | 1,812 bytes / 30 lines | unchanged | 5 | `734f4d6cb4f2e6b759097159d02db0bbed0ebba05bc465d34d8ea10edb967523` |
| `HANDOFF.md` | 660 bytes / 13 lines | unchanged | 1 | `ee075e4aae83133cb5ed41de36f8c9ffbdcedde5c12dffd1d5a96391b6e3ce90` |
| `README.md` | 3,006 bytes / 56 lines | unchanged | 5 | `f2aab5b3772ebad5baac4ea0995745bede92884abd8340451a960d03d80b771a` |

## No-loss ledger

Every heading in the four router surfaces is assigned exactly once. All 88
original headings are kept and one `Task declaration` heading is added.

| Surface | Ledger items | Disposition | Reason |
|---|---:|---|---|
| `AGENTS.md` original headings | all 77 | keep | Complete operating, safety, release, migration, and incident contract |
| `AGENTS.md` Task declaration | 1 | add | Routes future sessions through the installed gate before protected actions |
| `CLAUDE.md` | all 5 | keep | Claude-specific tool, operation, and commit guidance |
| `HANDOFF.md` | all 1 | keep | Concurrency-safe active-work pointer |
| `README.md` | all 5 | keep | Purpose, repository map, runtime shape, and setup routes |

Unassigned headings: **0**. Removed or unreachable instructions: **0**.

## Policy, trigger, and enforcement evidence

- Ordinary Markdown resolves to `prose`; ordinary application source resolves
  to `code`; repository rulebooks resolve to protected `reviewer-safety`.
- `vercel.json`, every GitHub workflow, and the Trigger.dev worker config
  resolve to protected `deployment` work.
- The Drizzle schema, canonical runner, drift checker, and every migration file
  resolve to protected `shared-db` work. The class name is the central engine's
  structural-database class; Oracle retains ownership of its own schema.
- A migration fixture refuses shipping with exit 3. Neither `--acknowledge` nor
  `--owner-request` bypasses it. A valid code flow proceeds.
- The pull-request workflow installs the commands from accepted ai-devops commit
  `4d83f9a5dc400f87408663eddac872b9074c18ed`, verifies the system-path command,
  and runs the focused fixture as a blocking assertion. GitHub Actions run
  `34376222705` proved that workflow green on the first pilot head.
- This pilot changes repository policy and tests only. It performs no database,
  application-row, Vercel, Trigger.dev, cloud, infrastructure, or production
  mutation.

## Rollback rehearsal

The focused test removes the declaration from a disposable Git fixture and
positively observes `vercel.json` fall from `deployment` to `code`. It restores
the declaration, observes `deployment` again, compares the policy byte-for-byte,
and proves an application-source hash did not change. Operational rollback is
the same bounded action: revert the pilot commit. No live-system rollback is
involved.
