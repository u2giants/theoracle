# Stage 8 bake-off — what we learned (2026-11-03)

This is a companion to the [stage-8 results](2026-11-03-stage-8-recommend.md) (PR #342). It records the method lessons, traps, and costs from running the stage-8 recommendations bake-off, so that the next model bake-off or production scale-up does not repeat them.

## Outcome
- Winner: `openai/gpt-6-luna`. Quality 0.797, best grounding (0.84), 20/20 JSON, no failures, about $5 at 100x scale.
- Runner-up: `z-ai/glm-5.3-flash`. Quality 0.760, fastest (7.5 s median), cheapest (about $2 at 100x).
- Rejected:
  - `qwen/qwen3.8-27b`: 5/20 answers were cut off mid-JSON even after retries, and it cost 15x more.
  - `meta/muse-spark-1.3-contributor`: marked only 2 of 20 findings as duplicates, against 6–10 for the other models, so repeat cards would reach the owner.
  - `anthropic/claude-haiku-5.5`: weakest grounding.
  - `deepseek/deepseek-v4.1-flash`: 6 truncated answers needed retries, and its p90 latency was 45 s.

## Lessons

1. **Model ids in Albert's list can be misspelled.** `qwen/qwen-3.8-27b` is not on OpenRouter; the real id is `qwen/qwen3.8-27b`. Check `/api/v1/models` first and record the spelling used. Do not silently swap in a different model.
2. **Truncated JSON is the main failure mode for reasoning-tier models at `max_tokens 4000`.** DeepSeek and Qwen both produced long answers that were cut off. The built-in `_Frontier.ask` retry recovered DeepSeek but not Qwen. Count retries in cost and in calls (DeepSeek: 26 calls for 20 findings; Qwen: 31).
3. **Duplicate-marking behaviour differs a lot between models**, and it decides how many cards Albert sees. Track the stored vs `duplicate_of`-dropped counts as a first-class metric.
4. **Building community reports is the expensive and slow prerequisite, not recommend itself.**
   - A full `run_communities` on the 97-chunk corpus produced 816 reports and 3,544 open questions: 682 Haiku calls, about 700k input / 1.6M output tokens, $0.87.
   - The six recommend runs together cost only $0.43.
   - Plan budgets around the reports step.
5. **`run_communities` makes O(n²) embedding calls.** `_store_open_questions` re-embeds every stored question on each insert. The uncached run made 3,196 embedding calls and ran for more than an hour. With an in-memory cache it finished in about 53 min. This is tracked in u2giants/theoracle#344. Any harness that runs communities on a real corpus needs that cache until the issue is fixed.
6. **Long jobs must be fully detached.** The 1Password `op_run` tool kills child processes when it times out (2 min default, 10 min maximum), and that wiped out a first reports run. The working pattern was a wrapper script that starts `setsid nohup uv run python …`, launched through `op_run`, which returns at once, and then waiting on the PID.
7. **Run candidates in parallel from one snapshot.** `createdb -T cmap_s8_base cmap_s8_<model>` creates one database per model. All six recommend runs finished within about 21 min wall time, and each database keeps that model's stored cards for later inspection.
8. **Sample deterministically.** Of the 54 qualifying findings, we used 5 company-level and 15 level-1 findings, ordered by a hash of the finding text, so every model saw the same 20.
9. **Judge side by side, and send it less text.** One judge call per finding graded all six answers under blind letters, which keeps scores comparable. The first judge pass (6 answers × 5k chars + 14k evidence) was slow and timed out under `op_run`. Cutting answers to 3.5k chars and evidence to 10k, writing each graded item to a progress file, and running the judge detached fixed it. Judge cost was about $0.03 per finding with Sonnet 5.5.
10. **Tell the judge not to fail answers for truncation you introduced.** JSON validity is measured separately on the full answer.
11. **`ai-doc-safety .` hung for more than 10 min** on this machine while several sessions ran it. A manual grep for LAN IPs, tokens, and project refs was used instead (u2giants/theoracle#345).

## Budget actually spent (OpenRouter, 2026-11-03)
| Item | $ |
|---|---|
| Reports build (one interrupted run plus one completed run) | ~1.40 |
| Six recommend runs | 0.43 |
| Judge (Sonnet 5.5, including one interrupted pass) | ~0.55 |
| **Total** | **~2.38** (limit 2.50) |

## Reusable assets on the test services host
- `cmap_s8_base`: `cmap_bake_5` plus Haiku-built community reports (graph version 1, 54 qualifying findings). It can be reused by any stage that needs reports, which saves about $0.87 and an hour. Clone it; do not modify it.
- `cmap_s8_{deepseek,glm,qwen,gpt6luna,haiku,muse}`: each candidate's stored recommendations.

## Open follow-ups
- u2giants/theoracle#344: fix the O(n²) open-question embedding.
- u2giants/theoracle#345: make `ai-doc-safety` finish, and add a changed-files mode.
- Before switching production, the coordinator decides whether recommend uses GPT-6 Luna (quality) or GLM-5.3 Flash (cost). The job brief and settings are the coordinator's to change.
