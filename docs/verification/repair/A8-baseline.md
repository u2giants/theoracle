# A8 baseline — Phase A of the Oracle repair plan (issue #520)

Recorded 2026-11-11 by Claude (Fable 5.2) on edge-dev3. Plan:
[plan_oracle_repair_and_consultant_upgrade.md](../../../plan_oracle_repair_and_consultant_upgrade.md).
All numbers were read from the production `cmap` schema (read-only). Times are New York (EST).

## What was released

| Item | Value |
|---|---|
| Pull requests | [#523](https://github.com/u2giants/theoracle/pull/523) (A1), [#524](https://github.com/u2giants/theoracle/pull/524) (A2–A7, A8 code), [#528](https://github.com/u2giants/theoracle/pull/528) (schema at start-up; Meta rescue retry) |
| Web version | `e8fe4ce5…` verified at `https://oracle.designflow.app/version.json` 11:04 AM; later docs-only merges do not rebuild |
| Brain image | `ghcr.io/u2giants/theoracle-brain:7ae581aa49fcff67a6babb4dadca6d6d11d3e622`, Coolify deployment `aq0lbrd1mugnmcndbrgwme1m`, `/health` ok at 12:07 PM |
| Schema | SQL 016–018 applied 11:04 AM (check constraint, `extraction.error`, `source.read_notes`, answer-source foreign key verified) |
| Actions run through the deployed brain | 11:04 AM `POST /eval/run`, `POST /jobs/retry-failed` (7), `POST /sources/reread-all` (57); 7:55 PM and 8:11 PM `POST /eval/run` |

## Before and after

| | Before (10:42 AM) | After (7:55 PM, rebuild finished) |
|---|---|---|
| Sources | 57 | 58 (one arrived during the run) |
| Sources by state | 57 `read` | 58 `read`, 0 `partial`, 0 `failed` |
| Sources shown `read` with nothing extracted | 0 | 0 |
| Passages (chunks) | 303 | 318 |
| Mentions | 4,832 | 5,000 |
| Entities | 2,070 (1,790 in one source only) | 2,199 (1,897 in one source only) |
| Relations | 2,311 | 2,773 (+20%) |
| Stored summaries, level 0 / 1 / 2 | 1,417 / 1,178 / 23 | 48 / 90 / 13 |
| Summaries of the current version, level 0 / 1 / 2 | 38 / 32 / 1 | 48 / 38 / 1 |
| Jobs failed | 7 | 0 (1,363 done) |
| Passages with a recorded extraction failure | not recorded | 0 |
| Sources with "could not be read" notes | not recorded | 5 |
| Graph version | 32 | 39 |

Stored level-1/level-2 summaries above the current version's count are the previous version (kept by design: newest two versions) and rows a recommendation or review flag still points at.

During the run 13 passages failed on the fault fixed in #528 (a retry parameter Meta's API rejects); all were re-extracted cleanly after that release.

## Self-test (15 questions, grader seat unchanged)

| Run | When | Graph version | Mean |
|---|---|---|---|
| Last run before this work | 2026-11-10 2:44 PM | 32 | 0.378 |
| After A1 + one rebuild, before the re-read | 12:03 PM | 35 | 0.422 |
| **A8 baseline run 1** | 8:06 PM | 39 | **0.364** |
| **A8 baseline run 2** | 8:22 PM | 39 | **0.409** |

Baseline for later phases: **0.39** (mean of the two runs, 0.364 and 0.409).

**Reading of the result.** Phase A removed the silent losses (no failed jobs, no failed passages, no stale summaries in answers, 20% more relations) but did not lift the score: the two baseline runs (0.364, 0.409) sit at the pre-repair level, below the 0.6 target. Per-question scores are graded in thirds over 15 questions, so one question changing by one step moves the mean by 0.022; the spread between 0.36 and 0.42 is three such steps and is within run-to-run variation (8 of 15 questions scored identically in the 12:03 PM and 8:06 PM runs; 4 went down a step, 2 went up). The remaining gap is the structural one the plan assigns to later phases: 86% of entities still appear in a single source, answers are not scoped by function (C4), relations stop at passage edges (E1), and the question set itself is unapproved and partly about fixture content (B1). Phase B (a trustworthy, owner-approved measure) is next, as planned.

## Live gates

- A1: answers read only the current version (code + tests); stored summaries fell from 2,618 to 151; scores above.
- A2: 0 failed jobs; no source `read` with zero mentions; failures now retried and recorded.
- A3–A7: re-read produced 318 passages from the same files (303 before) with no reading failures; 5 sources carry visible "could not be read" notes.
- A8: this file.

## Not verified here

- The new sources-page buttons and the "Parts that could not be read" list were not looked at in a live browser (type-checked; browser suite passes).
- Review flags and recommendations created before the re-read may point at entities that were re-created with new ids (plan drift log; step G1).
- Cost of the re-read was not read from the provider; flat extraction used about 30–36 thousand tokens per passage.

## Lessons for whoever runs the next full re-read or release

- Call `POST /sources/reread-all` alone. Requeueing old failed jobs first (`/jobs/retry-failed`) puts them at the front of the single worker's queue: an old full summary build and five old relations jobs ran for about 70 minutes before any source was re-read.
- A full re-read took about 8.5 hours end to end on 2026-11-11 (reading 20 min, facts ~2 h, relations ~1.75 h, name matching ~1.5 h, then projection, summaries and recommendations), on one worker.
- The brain is deployed by pinning `BRAIN_IMAGE_TAG` to the full commit SHA through the Coolify API and then `POST /deploy?uuid=…`; a restart orphans the running job, which is requeued after 180 seconds.
- Production steps need `ai-task-gates start --class production` and `--acknowledge` with the owner's exact words; class `deployment` refuses database actions outright.
- On 2026-11-11 GitHub's runners could not resolve `security.ubuntu.com`, failing the browser check before any test ran (#523, #524); the suite passed locally and in CI on #528.
- A long wait inside the 1Password `op_run` tool times the tool out; use a background timer and a read-only query instead.
