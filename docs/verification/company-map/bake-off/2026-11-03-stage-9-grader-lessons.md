---
summary: Reasoning and method details from the stage 9 evaluation-grader bake-off of 2026-11-03.
kind: proof
status: done
read-when: re-running or questioning the grader model choice
---

# Stage 9 grader bake-off — what we learned (2026-11-03)

Companion to the results in
[2026-11-03-stage-9-grader.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-9-grader.md)
and [its JSON](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-9-grader.json).
This file records the reasoning, the method details that are not in the results
table, the owner decisions, and the pitfalls hit along the way, so the next
grader bake-off can be run cold.

## 1. Outcome in one paragraph

Five of six candidates were available on OpenRouter (qwen/qwen-3.8-27b was not
listed under any id). On 35 items (30 stored answers + 5 deliberately corrupted
ones), openai/gpt-6-luna was the best cheap grader (0.895 point agreement, 9/9
planted contradictions found, 9/10 repeat-stable, ~$0.004 per 20-question run),
with anthropic/claude-haiku-5.5 as runner-up (missed 2/9 contradictions).
A two-sentence revision of `prompts/grade.md` was then tested, approved by
Albert ("yes"), and merged (PR #335): Luna rose to 0.933 and Sonnet 5.5 to 0.99
on the same set. Sonnet 5.5 remains the recommended frozen grader for the
current cycle; Luna is the cheaper successor-in-waiting, switched only between
cycles.

## 2. Owner decisions and questions in this session

| When (EST) | Albert said / asked | Result |
|---|---|---|
| 12:19 PM | "Sonnet 5.5 outperformed GPT-6 Luna significantly?" | Answered: no, not fairly measured — see §4. |
| 12:20 PM | "do you see a way to change the prompt/instructions to Luna to get it closer to sonnet 5.5?" | Diagnosed Luna's misses, tested a prompt revision (§5). |
| 12:24 PM | "yes" (adopt revised instructions, after re-checking Sonnet on them) | Sonnet re-run, prompt merged in PR #335. |

## 3. Data source facts (useful for the next grader test)

- Stored eval results live in `cmap.eval_run.results` (JSONB array; each entry
  has `question`, `expected_points`, `answer_md`, `covered`, `missing`,
  `contradicted`, `score`, `cited_sources`).
- On the test services host: `cmap_bake_1` had 3 runs, `cmap_bake_2` 1,
  `cmap_bake_3` 1, `cmap_bake_4` 0, `cmap_bake_5` 2, `cmap_bake_6` 2,
  `brain_test` 0 — 45 graded results in total, all graded by the retired
  `anthropic/claude-sonnet-4.5` seat.
- Those 45 results are only **5 questions × 9 distinct answers**. Every
  question has exactly 3 expected points. The score distribution was skewed
  low (19 of 45 at 0.0, only 3 at 1.0), so a grader test drawn from this pool
  is dominated by "missing" labels. A larger and more varied question set would
  make the next comparison stronger.
- The stored sonnet-4.5 grades disagreed with Sonnet 5.5 on several items
  (e.g. item 6 point 0 stored as contradicted, item 17 point 0 stored missing);
  the old grades are not a usable gold standard by themselves.

## 4. Why "Sonnet 98% vs Luna 90%" overstates the gap

The reference grading was Sonnet 5.5's own output plus a human review of the
disagreements (two overrides: item 18 point 0 and item 29 point 0 → covered).
So Sonnet's agreement number is largely self-agreement. The reference-free
measures are close: both found 9/9 planted contradictions and both were 9/10
repeat-stable. Sonnet's real edge was 0 false contradictions vs Luna's 4.
Lesson: when the judge is also a candidate, report its agreement but never rank
it on that number; build the reference with at least one independent reviewer
pass, or use a second judge for the disputed points.

## 5. The prompt fix — diagnosis and evidence

Luna's 11 disagreements with the reference fell into two patterns:

1. **False "contradicted".** Luna marked a point contradicted when the answer
   only said the data does not show/confirm/measure it, or named other causes
   alongside it (items 0, 1, 9, 18).
2. **Refusing "covered" on hedged facts.** When a cited sentence stated the
   fact but hedged (Jessica named in one source, the Licensing Manager role in
   another; "may be the same person"), Luna marked it missing (items 19, 25,
   27, 29; similar for 15, 28).

The revision replaced the one-line contradicted rule in `prompts/grade.md` with:
contradicted = a positive assertion that cannot be true if the point is true
(different number, person, order or outcome); "data does not show" is missing;
mentioning other causes is not a contradiction; and a hedged but cited
statement of the fact is covered.

| Model | Agreement old → new | False contra. | Stable |
|---|---|---|---|
| gpt-6-luna | 0.895 → 0.933 | 4 → 3 | 9/10 → 8/10 |
| claude-sonnet-5.5 | 0.981 → 0.990 | 0 → 0 | 9/10 → 8/10 |

Luna and Sonnet agree on 92% of point labels when both use the new prompt. The
stability dip shows in both models on a 10-item sample and is treated as noise;
re-measure on a larger repeat set before relying on it. Planted-contradiction
recall stayed 9/9 for both, so the stricter definition did not blunt real
contradiction detection.

**Consequence:** the `grade.md` prompt hash changed, so eval scores stored
before PR #335 are not directly comparable with later ones. Compare runs only
within one prompt hash (`cmap.eval_run.prompt_hashes`).

## 6. Per-candidate character (beyond the table)

- **gpt-6-luna** — balanced; slight strictness (−0.05 mean score bias), never
  generous. Medium latency (median ~3.4 s, p90 ~9.5 s on the old prompt, ~6.6 s
  p90 on the new one).
- **claude-haiku-5.5** — fastest strong model (median 1.8 s), unbiased score,
  but the generosity failure the job brief warns about: missed 2/9 planted
  contradictions.
- **deepseek-v4.1-flash** — good agreement but least stable (7/10) and emits
  heavy reasoning output (~50k completion tokens for 45 calls), so slow (p90
  ~22 s). One background run appeared to hang before the per-model timeout was
  added.
- **muse-spark-1.3-contributor** — finds every contradiction but over-calls
  them (10 false), slowest (median ~15 s).
- **glm-5.3-flash** — cheapest and fast but generous (+0.15 mean score bias)
  with the weakest correlation (0.64); missed 3/9 contradictions. Not fit as a
  grader.
- **Sonnet 5.5 (judge)** — 26 of 45 raw replies were not bare JSON (wrapped in
  a code fence), but the production parser recovered all of them, so 0 grade
  failures. Worth knowing if anyone ever tightens the parser.

## 7. How the test was built (re-run recipe)

1. Read-only export of every `results` element from the eval runs above;
   de-duplicate on (question, answer).
2. Sort by stored score and take 30 evenly spaced items; append 5 hand-written
   corrupted answers, one per question, each mixing correct cited sentences
   with planted contradictions (9 contradictions total).
3. Grade with the fixed judge, then manually review every point where judge,
   stored grade, or planted expectation disagree; record overrides.
4. For each candidate, call the production `grade_answer` with
   `BRAIN_EVAL_MODEL` set in that process only, wrapping `_post_chat` just to
   capture latency and token usage; grade all 35 once and every 3rd item a
   second time (10 repeats). 6 parallel workers.
5. Score: point-label agreement, Pearson score correlation, planted
   contradiction recall, false contradictions, mean score bias, repeat
   stability, raw JSON validity, latency, tokens and $ (OpenRouter list price).
6. To test a prompt variant, point the harness at an alternate prompt file
   (override `GRADE_PROMPT_PATH`) and tag the output; do not edit the real
   prompt until the owner approves.

The harness, item set (contains full answer text) and raw replies stayed in
the session scratch area and were not committed.

## 8. Operational pitfalls hit

- **Long synchronous secret-injected runs time out.** Running all models in
  one 1Password-injected command exceeded the tool's time limit with no
  output. Fix used: launch the loop detached with a per-model `timeout`, write
  a progress file, and wait on it in the background.
- **Repo-wide `ai-doc-safety` hung** for over 10 minutes and was stopped; it
  also rejects a single file path ("is not a git repository"). The results
  files were checked by hand for LAN addresses, project refs and keys (none
  found). The scan itself never completed — see §9.
- **`bin/ai-pr-wait` is not in this repo**; the installed `ai-pr-wait` exists
  but its 9-minute wait outlived the tool call. Checks were read once with
  `gh pr checks` and all passed before merging. Hand-written sleep+poll loops
  are blocked by a hook.
- Spend for the whole session was about $0.40 of the $2.50 stage budget.

## 9. Open items

- The public-boundary scan (`ai-doc-safety`) never completed on PRs #329/#335
  or this file; manual check only. Next step: run it on a clean checkout of
  `main` with a longer timeout, or fix why it hangs on this repository.
- The grader recommendation (keep Sonnet 5.5 frozen this cycle; Luna as
  successor) needs the coordinator to carry it into the consolidated job
  brief; this session did not edit the brief, by rule.
- Repeat-stability was measured on only 10 items; a 30-item repeat set would
  tell whether the 9/10 → 8/10 dip is real.
