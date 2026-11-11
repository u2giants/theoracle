---
summary: Lessons from the stage 7 question-answering bake-off of 2026-11-03 and what a re-run should do differently.
kind: proof
status: done
read-when: before re-running the answer-model comparison
---

# Stage 7 (question answering) bake-off — lessons learned

Companion to [`2026-11-03-stage-7-answer.md`](2026-11-03-stage-7-answer.md) (results) and its `.json`.
Written 2026-11-03, 4:35 PM EST, by the session that ran the stage-7 bake-off (PR #336).

This file explains how the run actually went and what a future re-run should do differently. Read it before you re-run stage 7, for example after Albert and Ilona finish the 20 questions, or before the global-mode test.

## 1. What was decided and why

- **Keep `anthropic/claude-haiku-5.5` in `BRAIN_CHAT_MODEL`.** The top three scores, 0.674–0.682, are a statistical tie on 20 draft questions. Haiku is the most honest about unknowns among those three, and leaving it in place costs nothing.
- **Runner-up: `z-ai/glm-5.3-flash`.** It costs about 4.5× less, but it answered **only** through the empty-content rescue retry: 20 of its 20 first calls came back empty. A seat whose only working path is a fallback is fragile.
- **Not recommended:**
  - `google/gemini-3.8-flash`: about 6–25× the price, one hard failure, and the lowest honesty score.
  - `openai/gpt-6-luna`: fast and cheap, but citation validity 1.25/5 because its quotes are not verbatim, so validation drops them and sentences are marked "(uncited)".
  - `deepseek/deepseek-v4.1-flash`: the best correctness and synthesis, but the slowest (p50 83 s) and 17 rescues.

## 2. Findings about the models (beyond the results table)

1. **Empty content is widespread, not a Haiku quirk.** Haiku (11 calls), DeepSeek (17) and GLM (20 of 20) all returned empty `content` on the first call in JSON mode with `max_tokens` 8000. Each spent its budget on hidden reasoning. The PR #307 rescue in `brain/llm.py` fixed every case: it doubles `max_tokens` and asks for low reasoning. No call was still empty after the rescue. **The rescue is load-bearing for three of the five models; do not remove or weaken it.** The extra call roughly doubles token use on rescued questions, and those costs are counted in the results.
2. **Gemini's failure was a cut-off JSON answer, not an empty one.** On q9 the `answer_md` string was cut off on all three `_ask` attempts. The salvage parser could not recover it, so the call raised `frontier answer failed after retries`.
3. **Exact quoting decides citation validity.** Local mode keeps a citation only if the quote is an exact substring of its chunk. Models that paraphrase (Luna most of all) lose most of their citations. The cause is model behavior, not a code bug.
4. **Latency varies widely.** Luna about 24 s, GLM about 45 s, Haiku about 58 s, Gemini and DeepSeek about 76–80 s mean per question. All are slow for a Teams chat reply; this matters for the employee-conversation work.
5. **Tokens per question are about 50k–130k in, 2k–16k out.** Retrieval caps keep this flat, so cost is per question and does not grow with the corpus. That is why the report gives cost per 1,000 questions rather than a 100× corpus multiplier.

## 3. Findings about the method (what went wrong and how it was fixed)

1. **Background jobs died with the secret runner.** Jobs launched with plain `&` inside a 1Password `op_run` command were killed when that command returned. **Fix:** launch with `setsid nohup … < /dev/null &`. They then survive and keep the secret only inside their own process environment.
2. **Ten parallel `op_run` calls all timed out.** The MCP request timed out before the long foreground runs ended. Partial results were kept because the harness appends one line per question. **Fix:** one short `op_run` that launches detached jobs, then wait with a background `until ! pgrep …` loop. The harness also skips questions already answered, so a re-launch resumes instead of repeating paid calls.
3. **The judge's first pass ran out of tokens on 35 of 100 answers.** `claude-sonnet-5.5` reasons before answering, and `max_tokens` 600 was used up before any JSON came out. **Fix:** regrade the failed rows with `max_tokens` 4000. Keep `grades.round1.jsonl` for audit. **Start a re-run at 4000** to avoid the wasted round.
4. **The run went over budget.** About $4.56 was spent against the $2.50 per-session limit. Gemini answering was $2.32 and the judge about $1.37. Next time, either test Gemini on 5 questions first and stop it if it is not clearly better, or budget for it explicitly. The key had $14.91 left at 12:21 PM EST, so the $5 floor was never crossed.
5. **The shared doc-safety scan stalled.** Several sessions ran `ai-doc-safety` over the whole repo on the same machine at the same time, and mine produced no output after more than 5 minutes. A targeted scan of the two report files (IP addresses, tailnet names, Supabase refs, key prefixes, home paths) plus green PR CI was used instead. Run the full scan when the machine is quiet, or one session at a time.
6. **`$TMPDIR` differs between the Bash tool and `op_run`.** The Bash tool uses a per-session `/var/tmp/...` folder and `op_run` sees a different one. Use absolute paths in `op_run` commands.
7. **The judge script needs the brain virtualenv.** A system `python3 -I` has no `httpx`; use `apps/brain/.venv/bin/python -I`.

## 4. Limits of this result (read before quoting the scores)

- **The questions are drafts.** Appendix A of `HANDOFF.d/2026-11-02T2057Z-edge-dev-mimo-model-overhaul-bakeoff-round2.md` has not been edited by Albert and Ilona yet. Scores compare models with each other; they are not an absolute quality number.
- **Only local mode was tested.** `cmap_bake_5` has no community reports, so global and auto mode, the map-reduce path and source-id citations are untested. Production `auto` routing sends broad questions to global mode, and many of the 20 questions are broad.
- **There is one judge and no human calibration.** Differences under about 0.03 are noise at n=20.
- **Each model was run once, at temperature 0.** Run-to-run variance was not measured.

## 5. How to re-run (cold-start recipe)

1. Clone the instrument: `docker exec brain2-test-pg createdb -U oracle -T cmap_bake_5 cmap_s7_<tag>`. Never touch `cmap_bake_1..6`.
2. Start your own graph on a free port: `docker run -d --name falkor-s7 -p 568xx:6379 falkordb/falkordb`. Never use the shared FalkorDB.
3. Set this environment, with secrets only as 1Password `op://` refs in `op_run`:
   - `DATABASE_URL` → the clone
   - `FALKORDB_URL` → your port
   - `BRAIN_EMBED_MODEL=openai/text-embedding-3-large`, `BRAIN_EMBED_DIMS=1024`
   - `BRAIN_SCALEDOWN_ENABLED=true`
   - the OpenRouter and ScaleDown keys
4. Project the graph once with `run_project()`. The expected graph is 969 nodes and 752 edges.
5. Run the harness, one detached process per model. The harness:
   - parses the 20 Appendix A questions;
   - wraps `brain.llm`'s `httpx.post` to record usage, empty content and rescue per call;
   - calls `answer_question(q, mode="local")`;
   - writes one JSONL line per question and skips questions already answered.

   The scripts (`run.py`, `judge.py`, `agg.py`) and all raw outputs are in the coordinator's shared notes folder under `s7-answer/`, outside the repo. If that folder is gone, rebuild them from this description.
6. Judge with `anthropic/claude-sonnet-5.5`, temperature 0, JSON mode, **max_tokens 4000**. The judge prompt covers the question, the final answer, the stated unknowns and the surviving citations with source titles. It scores five criteria 0–5; quality = sum ÷ 25, and a hard failure scores 0.
7. Clean up: `docker rm -f falkor-s7` and `dropdb cmap_s7_<tag>`.
8. Before each model, check `GET /api/v1/key` `limit_remaining`. Stop if it is under $5.

## 6. Recommended next steps (owner-held or coordinator-held)

- Re-run stage 7 on the **final** 20 questions once Albert and Ilona have edited them. Use Haiku, GLM, and DeepSeek if budget allows.
- Test **global/auto mode** once community reports exist (stage 6 output) on a cloned DB.
- If GLM-5.3-flash is ever considered for the seat, first confirm its first-call empty-content rate in production logs. Consider whether it should run with the low-reasoning setting from the start rather than only on retry.
