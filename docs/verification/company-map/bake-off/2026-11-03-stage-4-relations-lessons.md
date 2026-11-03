# Stage 4 relationship extraction — what the bake-off taught us (2026-11-03)

These are the session's lessons from the stage-4 bake-off (11:40 AM – 1:55 PM EST,
2026-11-03). The results tables are in
[2026-11-03-stage-4-relations.md](2026-11-03-stage-4-relations.md) and the
machine-readable form is in
[2026-11-03-stage-4-relations.json](2026-11-03-stage-4-relations.json). This file
covers the reasons behind the result, the things that went wrong, and what a
future re-run should do differently.

## 1. Bottom line

- **Pick for stage 4: `meta/muse-spark-1.3-contributor`.** It is tied for the
  best quality with full `z-ai/glm-5.3`, has had zero failed chunks across
  three runs, uses the widest spread of relation types, and costs about $7 per
  10,000 chunks.
- **Fallback if speed matters more than cost: `z-ai/glm-5.3`** (not Flash).
  Its quality is the same as Muse's, it is about 3x faster (11.5 s median per
  chunk against 38 s), and it keeps the most relations (281 against 210 on 25
  chunks). It costs about $39 per 10,000 chunks because its output tokens are
  priced 18x higher than Muse's.
- **Not usable today:**
  - `anthropic/claude-haiku-5.5`: hit the 2,000-token output limit on 56% of
    chunks.
  - `deepseek/deepseek-v4.1-flash-1017`: 40% of chunks came back empty.
  - `inclusionai/ling-3.1-flash`: 88% of chunks failed.
  - ScaleDown Extract: precision too low (see §6).
- `z-ai/glm-5.3-flash` and `openai/gpt-6-luna` were reliable but mid-pack.
  Flash had the lowest precision of the reliable models, at 0.58 in the second
  grading pass.

## 2. How quality was measured, and how far to trust it

- The sample was 25 non-chatter chunks of the real 97-chunk corpus, chosen
  deterministically with `ORDER BY md5(id::text) LIMIT 25`. Every model saw
  exactly the same chunks, mentions and previous-chunk context, built by the
  production functions `known_mentions`, `build_prompt` and `last_sentences`
  in `apps/brain/brain/extract/relations.py`. The model output went through the
  production `parse_relations_json` and `validate_response` unchanged, so
  "kept" means "would have reached the database".
- **Precision** comes from a seeded random sample of 40 kept relations per
  model, judged by `anthropic/claude-sonnet-5.5`. The judge saw the chunk text
  and graded all models' relations for that chunk together in one call.
- **Recall** is relative, not absolute. It is measured against the union of
  every link the judge approved across all models, keyed by chunk and
  unordered entity pair. A model's recall therefore depends on which other
  models were in the pool: adding GLM-5.3 and Extract grew the union from 126
  to 149 to 166 pairs, and everyone's recall fell. Compare recall only within
  one grading pass.
- **The judge's noise is about ±0.05 to 0.10 in precision between passes.** The
  same Muse outputs scored 0.80, 0.775 and 0.725 across three passes, and
  GLM-5.3 scored 0.75 and then 0.80. Muse and GLM-5.3 led in different passes.
  That is why the report calls them tied rather than naming a quality winner.
  Separating them would take 100 or more judged relations per model, or a
  human-checked gold set.
- Historical reference only: the earlier full-corpus counts were GLM 946,
  gemini-3.1-flash-lite 360 and sonnet-4.5 862. These are not comparable to
  the 25-chunk sample.

## 3. Failure modes seen, by model

- **Empty content after the rescue retry** (DeepSeek, Ling). `brain/llm.py`
  retries once with `reasoning: {effort: low, exclude: true}` and double the
  token budget. Both models still returned `content: null`. DeepSeek did this
  on 35 attempts and Ling on 47. These count as stage failures. Even when
  DeepSeek succeeded, it was slow (51 s median per chunk) because it spends
  most of its tokens thinking: it used 44,669 output tokens for only 70 kept
  relations.
- **Provider rate limits (429)** for Ling: 21 times. Together with the empty
  answers, one 25-chunk run took 29 minutes. A Ling re-test is only worth it if
  a different OpenRouter provider becomes available.
- **Truncation at `max_tokens=2000`** (Haiku: 14 of 25 chunks). Haiku writes
  long descriptions and runs out of room on dense chunks. The salvage path
  (`_complete_items`) keeps the complete items, but the tail relations are
  lost. The job brief allows truncation on fewer than 2% of chunks. Raising
  `MAX_TOKENS` could rescue Haiku, but that is a code change outside a
  bake-off.
- **Even the good models truncate on a few chunks:** Muse 4, GLM-5.3 8 and
  GLM-5.3 Flash 6 of 25. This is well above the brief's 2% target for every
  model. It is a pipeline issue, not a model issue: the densest process chunks
  need more than 2,000 output tokens, or a split.
- **Validator drops:** raw against kept was Muse 240 → 210, GLM-5.3 Flash
  267 → 218 and Luna 220 → 188. The usual causes are a quote that is not an
  exact substring, or an unknown key.

## 4. Cost lessons

- Output tokens dominate the cost at this stage. Every model's output was
  equal to or larger than its input (about 1,200 input tokens per chunk). So
  the output price, not the input price, decides the bill. GLM-5.3's output
  price is $3.60 per million tokens against Muse's $0.20, which is why the two
  are tied on quality but 5.5x apart on cost.
- Use OpenRouter's reported `usage.cost`. It matched the token × price
  calculation and needs no assumptions.
- Projection: corpus $ = sample $ ÷ 25 × 97, and 100x $ = sample $ ÷ 25 ×
  10,000. The whole session spent about $0.75 of OpenRouter credit, including
  three judge passes at about $0.18 each, well under the $2.50 cap.
  ScaleDown Extract cost under $0.01 in total.

## 5. Operational lessons (for whoever runs the next bake-off)

- **The 1Password `op_run` tool times out after about 1–2 minutes and can drop
  the connection** on long jobs. Running six models inside one `op_run` call
  failed twice with no output. What worked: use `op_run` only to launch a
  detached job (`nohup setsid bash script.sh &`) with the secret in that
  process's environment, write results to files, and wait on a sentinel line
  in a log with a bounded Bash loop.
- Run models one after another, with 8 threads inside each model, the same as
  production. A stalled model (Ling) blocks the rest, so give each model a
  timeout.
- **Never modify `cmap_bake_*`.** A clone made with `createdb -T cmap_bake_5
  cmap_s4_relations` takes seconds. The clone was dropped after each run.
  Grading only reads chunk text, so it can read `cmap_bake_5` directly.
- **`ai-doc-safety` on the full repository can stall for more than 20
  minutes** when several sessions run it at once: all of them sat in the same
  `git grep … ts.net` step. A fast, equivalent gate is to copy only the
  changed doc files and the allowlist into a scratch git repository and run
  `ai-doc-safety <that dir>`. It passed in seconds every time.
- `gh pr merge --admin` straight after a push can fail with "not mergeable"
  while GitHub computes mergeability. Re-check `mergeable` once and merge. Do
  not use sleep-then-poll, which the poll-guard hook blocks.
- Albert's later requests (full GLM-5.3, ScaleDown) each needed one more
  grading pass over all models together, so the numbers stay comparable. Keep
  every model's raw results file until the session closes.

## 6. ScaleDown Extract — why it can't do this job well

Albert asked whether ScaleDown's Extract model could match Muse, trying
several prompt designs.

- **What Extract is:** a schema-driven span finder (ScaleDown's own API,
  `model: "extract"`, `response_format: json_schema`, with a system message as
  the global instruction). It is not a chat model, so `prompts/relations.md`
  cannot be sent as-is. Nested arrays of objects are supported (up to 200
  items) and come back in `structured_result`. The price is $0.05 per million
  input tokens, and output is free.
- **Six designs were tried.** The kept counts below are for the first four
  chunks; Muse kept 30 on the same four chunks.

  | Design | What changed | Kept / raw |
  |---|---|---|
  | v1 | one array of links, free-text type, full instruction | 5 / 19 |
  | v2 | v1 with a minimal instruction | 1 / 22 |
  | v3 | one array per relation type | 18 / 77 |
  | v4 | v3 plus direction and "prefer specific types" guidance | 34 / 107 |
  | v5 | v4 plus an adapter that repairs near-miss quotes and fuzzy-maps entity names | 50 / 91 |
  | v6 | v5 plus "copy names exactly from the list" | 49 / 74 |
- **Lesson 1:** one array per relation type works far better than a single
  array with a type field. Extract treats each property name as the thing to
  look for, so naming the property "performs links" steers it in a way a
  type field does not.
- **Lesson 2:** Extract rarely copies entity names or quotes exactly. It
  paraphrases quotes and invents names such as "NOT PERMITTED". Without a
  repair adapter, most of its links fail the production validator. Any real
  integration would need that adapter.
- **Result on all 25 chunks, in the same grading pass:** v6 scored F1 0.45
  (precision 0.50, recall 0.42). v5 matched Muse's recall (0.48) but had
  precision 0.15. Muse scored 0.58 and GLM-5.3 0.62. Extract never produced
  EXCEPT_WHEN or CONTRADICTS links, which the brief ranks as the second
  priority.
- **Where Extract might still fit:** finding mentions (entity spans) is its
  natural job, not typed links between them. That is a stage-3 question; it
  was not tested here.

## 7. Open threads (not done in this session)

- Truncation at 2,000 tokens affects every model on the densest chunks. A
  code-side fix to raise `MAX_TOKENS` or split chunks is a separate decision
  for the coordinator.
- The quality tie between Muse and GLM-5.3 is within the judge's noise. If the
  choice matters, a larger judged sample or a human-checked gold set would
  settle it.
- The coordinator applies the winner in the job brief and settings. This
  session did not change any production setting.
