# Stage 3 flat extraction: what the 2026-11-03 session learned

Session ran 11:39 AM – 5:05 PM EST on 2026-11-03 on the test services host. Owner: Albert Hazan. Raw numbers and method are in
[2026-11-03-stage-3-flat-extraction.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-3-flat-extraction.md)
and the machine-readable
[.json](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-3-flat-extraction.json).
This file explains what those numbers mean, what was decided, and what to watch.

## 1. Decisions and current state

| What | State | Where |
|---|---|---|
| Passage labels (process / rule / chatter …) | **ScaleDown `/classify` with the richer label descriptions** — in production code | PR [#338](https://github.com/u2giants/theoracle/pull/338) |
| Finding the items in each passage (entities) | **z-ai/glm-5.3-flash**, selected by the new env var `BRAIN_FLAT_MODEL` | PR [#349](https://github.com/u2giants/theoracle/pull/349) |
| Production env value `BRAIN_FLAT_MODEL=z-ai/glm-5.3-flash` | **Not set yet.** Handed to the bake-off coordinator session, which seats all stages together | Coolify app `oracle-brain` |
| Fallback when ScaleDown is down | same `BRAIN_FLAT_MODEL` (else `BRAIN_FRONTIER_MODEL`) answers `prompts/flat_extract.md` | `apps/brain/brain/extract/flat.py` |

Owner words that set this: "switch ScaleDown to the richer passage labels and keep playing around with different options for the descriptions to get it to match GLM", then, after the results, "then keep z-ai/glm-5.3-flash for descriptions".

Behaviour with `BRAIN_FLAT_MODEL` set: per chunk, one ScaleDown `/classify` call plus one GLM call; ScaleDown `/extract` is skipped; the label still comes from ScaleDown (the GLM answer's own label is ignored when ScaleDown answered). Unset: identical to the previous behaviour. Live check on 3 real chunks: records were `scaledown/classify` + `z-ai/glm-5.3-flash`, 0 ScaleDown extract calls.

## 2. The candidate bake-off (frontier fallback seat)

Same 25 real chunks, production prompt and code path, judged by anthropic/claude-sonnet-5.5 (pooled reference).

- **GLM-5.3-flash**: best value. F1 0.75 (0.71 after the reference grew), precision 0.86, ≈ $0.11 for the current 97-chunk corpus, ≈ $12–15 per 10,000 chunks. Slow: ≈ 96 s median per chunk (hidden reasoning, ≈ 13k output tokens per chunk).
- **DeepSeek V4.1 Flash**: same F1 as GLM, more recall, less precision, 12x the cost (≈ $143 / 10k) and ≈ 2 min per chunk. Runner-up.
- **Qwen3.8-27b**: most recall, least precision, ≈ $642 / 10k, slowest. Not suitable. Albert's id `qwen/qwen-3.8-27b` is not a catalog id; `qwen/qwen3.8-27b` was tested.
- **GPT-6 Luna, Claude Haiku 5.5**: very precise but find only about half the items — the "shallow extraction" trap the job brief warns about.
- No candidate returned broken JSON or empty content; the empty-content rescue was never needed.

## 3. What we learned about ScaleDown

1. **Speed**: ≈ 4 s per chunk for both calls, 20x faster than GLM.
2. **It is good at people and software, weak at everything abstract.** Share of the judged items it found (tuning set): people 47/53, systems 19/25 — near GLM; documents 97/179, processes 13/35, departments 30/47, products 11/25 — clearly behind GLM; problems and exceptions almost never (both engines are weak there).
3. **Richer *label* descriptions help a lot.** Rewriting the seven passage-kind descriptions, and telling it "not chatter if it names any system, document, brand, customer, team, rule or work step", raised label accuracy from 0.60 to 0.76 (0.79 on unseen chunks) with zero wrongly skipped passages. Now in production.
4. **Richer *entity* descriptions hurt.** Long descriptions with examples lowered recall (0.53 → 0.47). Best guess: longer descriptions dilute ScaleDown's matching. Very short descriptions (3–6 words) were slightly better than the current ones (+0.01–0.02 F1) — within noise.
5. **Splitting the types across several calls does not help on its own.** Three groups of types, or one type per call (16 calls), score about the same as one call, and the type labels get worse (0.86 → 0.65 for one-per-call).
6. **Combining several ScaleDown passes does help, but not enough.** Merging the answers of differently-worded passes raises recall past GLM, but adds wrong items:

   | ScaleDown setup | Calls per chunk | F1 on unseen chunks |
   |---|---|---|
   | current | 1 | 0.647 |
   | current + short descriptions | 2 | 0.687 |
   | current + short + three groups | 5 | 0.698 |
   | GLM | 1 (model) | **0.754** |

   That ≈ 0.05 gap on unseen chunks, plus 2–5x the ScaleDown calls, is why Albert chose GLM for item-finding.
7. ScaleDown's confidence scores are honest-looking (most items 0.9–1.0, a tail below 0.5 that the 0.5 cut removes); ≈ 125 of its raw items per 25 chunks are dropped by that cut and the span check.

## 4. Things to watch

- **GLM wrongly called one meeting excerpt "chatter"** (score 0.85) on the tuning set. With ScaleDown now doing the labelling this does not happen in production — but it would come back if ScaleDown is turned off (GLM then labels too).
- **GLM speed**: ≈ 1.5 min per chunk at 8 chunks in parallel means a 400-chunk source takes ≈ 75 minutes for this stage. Fine for background work; worth re-checking at the 10,000-chunk scale.
- **Judge reference grows with every new run** (pooled judging). Compare scores only within one scoring pass; that is why GLM shows 0.748 in the first table and 0.708 later on the same chunks.
- **Problems and exceptions are rarely found by anyone.** If the map needs them, a dedicated pass or prompt change is a future job, not tried here.

## 5. How the measurements were made (to repeat them)

- Test copy of the real-corpus database `cmap_bake_5` (97 chunks), cloned per session, flat mentions wiped, dropped after use. Never the shared originals.
- Tuning set: every 4th chunk (by source, order), first 25. Unseen set: every 4th from offset 2, 24 chunks.
- Each run called the production functions in `brain/extract/flat.py` (`_post_chat` / `_post_scaledown`, `parse_model_json`, `mentions_from_entities`, `is_chatter`) so spans, confidence cut and chatter rule match production exactly.
- Judge: per chunk, the pooled set of every run's accepted items was marked valid/invalid with a best type, missed items were added, and the right passage kind given. Precision = valid share of a run's items; recall = share of all valid items it found.
- Spend: ≈ $2.2 for candidates, ≈ $0.6 for judging, ≈ $0.4 for the unseen-set GLM run and follow-up judging. ScaleDown calls are on its own plan.
- Practical notes: the 1Password run tool times out on calls longer than a few minutes — start long runs detached and wait on their log. GLM's 25-chunk run takes ≈ 6–11 minutes.
