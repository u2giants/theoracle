# Stage 5 (entity resolution) bake-off — lessons learned (2026-11-03)

Companion to [the stage-5 results](2026-11-03-stage-5-resolve.md) and [its JSON](2026-11-03-stage-5-resolve.json). Follow-up issue: [u2giants/theoracle#353](https://github.com/u2giants/theoracle/issues/353).

## 1. Outcome in one paragraph

All four candidates Albert named (anthropic/claude-haiku-5.5, deepseek/deepseek-v4.1-flash, openai/gpt-6-luna, meta/muse-spark-1.3-contributor) were available on OpenRouter and finished a full re-resolve of the real corpus (2,077 mentions, 97 chunks). **openai/gpt-6-luna won** (judged merge precision 0.87, description faithfulness 0.88, zero failures, $0.046 for the corpus). **Muse Spark 1.3 Contributor was runner-up** (best precision 0.92, but 3–4x slower, 2x the cost, weaker descriptions). The most important finding is not about models: the fixed matching rules decide most of the duplicate/non-duplicate outcomes, and they get many of them wrong (issue #353).

## 2. How resolve actually works (what matters for any future eval)

- `run_resolve` only touches mentions with `entity_id IS NULL`. To re-run the stage on an already-resolved DB you must, inside one transaction: delete `cmap.resolve_decision`, delete `cmap.entity_alias`, set every `cmap.mention.entity_id = NULL`, delete `cmap.entity` (in that order — alias and decision rows have foreign keys to entity; nothing else does). Relations and chunks are untouched.
- Rules in order: alias table → exact normalized-name match → Person first-name/initials (rule 3) → embedding cosine ≥ 0.92 auto-merge (rule 4) → model judge for candidates in cosine [0.80, 0.92) (rule 5) → new entity.
- On this corpus the split was roughly: ~970 new, 705 alias, ~383 embedding, 2 name-part, and only **14–20 judge merges** out of ~161 judge calls. The model therefore decides very few merges; the describe step (~178 calls) is half of the frontier traffic and most of the tokens.
- The describe step also calls the embedding model once per described entity, so `BRAIN_EMBED_MODEL` must be set (we used `openai/text-embedding-3-large`, matching how `cmap_bake_5` was built).
- `duplicate_of` is not a resolve field. It belongs to the recommendations stage (`prompts/recommend.md`). The brief's mention of it for stage 5 was a mix-up.

## 3. Measurement method that worked

- One `createdb -T cmap_bake_5 cmap_s5_<slug>` clone per candidate inside the `brain2-test-pg` container, all four runs in parallel (each process has its own `DATABASE_URL` and `BRAIN_FRONTIER_MODEL`, so the shared-env concern for heavy stages does not apply when processes are separate).
- Instrumentation without code changes: monkey-patch `brain.resolve.resolve.post_chat_with_rescue` in a wrapper script to record call kind (judge vs describe, detected from the prompt text), latency, prompt/completion tokens and OpenRouter `usage.cost`, and empty content.
- Grading with a fixed grader (`anthropic/claude-sonnet-5.5`): every judge merge plus 10 random rejections (seed 5) re-judged; 8 random descriptions scored 0–1 for faithfulness to their quotes; plus a hand-built list of 23 true alias pairs and 18 different-thing pairs, checked by whether both names share an entity.
- Grading cost was about $0.08 per candidate; total spend for the stage was well under the $2.50 budget.

## 4. Findings

1. **Rules dominate.** All four models produced the same pair results: 19–20 of 23 known duplicates missed and the same 6 of 18 different things fused. Fusions (Walmart/HomeGoods, TJ Maxx/Marshalls, Disney/NBC Universal, Marvel/DC Comics, Lic Manager/Lic Coordinator, Creative Designer/Technical Designer) come from the 0.92 embedding auto-merge. Misses (DFlow/DesignFlow, Click Up/ClickUp, NBC Universal/NBCUniversal, Jen/Jen Chaffier) are either below the 0.80 judge floor or blocked by spacing differences in `normalized_name`. Swapping models cannot fix this.
2. **Judge errors are rare and similar across models**: 1–2 false merges each, always a vague phrase ("submit", a problem sentence) absorbed into a nearby Step or Issue. Rejections were 100% correct for every model. With only 11–15 gradable merges per model, precision differences are within one decision.
3. **Descriptions are where models differ.** gpt-6-luna (0.88) and DeepSeek (0.89) stayed close to the quotes; Muse 0.77; Haiku 5.5 0.62 with invented step names.
4. **Reliability and cost:** DeepSeek returned empty content 3 times (recovered on retry) and burned reasoning tokens (most expensive, $0.15). Muse wrote 411k output tokens and took 56 minutes wall time. Haiku was fastest (12 minutes, p95 3 s). gpt-6-luna used the fewest output tokens (51k).
5. **Projected cost** scales roughly linearly: at 100x corpus, about $4.60 (gpt-6-luna), $8 (Haiku), $10 (Muse), $15 (DeepSeek) per full re-resolve.

## 5. Operational lessons (things that went wrong)

- **Background runs died with their launcher.** Runs started with `nohup … &` inside the 1Password `op_run` shell were killed when that shell exited; the DBs were left half-resolved and no logs were written. Fix: launch with `setsid nohup … < /dev/null &`. After a kill, reset the clones fully before rerunning so token counts cover the whole pass.
- **`pkill -f` matched my own shell** (exit 144). Use a narrower pattern such as `python.*run_s5`.
- **`op_run` has a 10-minute cap**; long grading must run detached, not inside `op_run` in the foreground.
- **`ai-doc-safety` scans the whole repo** and takes several minutes; run it in the background before merging.
- Clone DBs were dropped after grading; recreate from `cmap_bake_5` with the reset in §2.

## 6. Recommendation and next steps

- Seat stage 5 on `openai/gpt-6-luna`, Muse as fallback (coordinator consolidates; no prod env was changed here).
- Fix the matching rules before the 100x corpus: issue [#353](https://github.com/u2giants/theoracle/issues/353) has the pair list and the done-when.
- A larger judge sample needs a bigger corpus; at today's size only ~15 merges per model are gradable.
