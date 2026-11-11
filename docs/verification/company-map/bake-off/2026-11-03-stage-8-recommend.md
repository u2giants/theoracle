---
summary: "Results of the stage 8 recommendations bake-off of 2026-11-03: winner GPT-6 Luna, runner-up GLM 5.3 Flash."
kind: proof
status: done
read-when: checking the recommendations model choice
---

# Stage 8 — Recommendations bake-off (2026-11-03)

Function under test: `brain/recommend/recommend.py` `run_recommend`, one candidate per run via `BRAIN_FRONTIER_MODEL`. Judge: `anthropic/claude-sonnet-5.5` (fixed). Run 11:41 AM – 2:21 PM EST on the test services host.

## Winner

**`openai/gpt-6-luna`** — highest judged quality (0.797), best evidence grounding (0.84), 20/20 valid JSON, no failures, ~14 s median, $0.054 for the current corpus.

**Runner-up: `z-ai/glm-5.3-flash`** — quality 0.760 (statistically tied with DeepSeek, ahead on open questions), fastest (7.5 s) and cheapest ($2.19 at 100x scale vs $5.37). Choose it if cost at scale matters more than the ~4-point grounding gap.

Not recommended: `qwen/qwen3.8-27b` (5/20 findings failed, 15x the cost), `meta/muse-spark-1.3-contributor` (flags almost no duplicates → repeat cards), `anthropic/claude-haiku-5.5` (weakest grounding), `deepseek/deepseek-v4.1-flash` (good quality but 6 truncated answers needing retry and a 45 s tail).

## Candidates and availability

All six ids from Albert's list exist on OpenRouter `/api/v1/models` (checked 2026-11-03, all support `response_format`), except `qwen/qwen-3.8-27b`: not listed; the same model is listed as `qwen/qwen3.8-27b` (spelling only, no hyphen) and was tested under that id. Prices per million tokens (input / output, OpenRouter, 2026-11-03): DeepSeek $0.045/$0.50; GLM $0.0313/$0.0846; GPT-6 Luna $0.10/$0.50; Haiku 5.5 $0.10/$0.50; Muse $0.10/$0.20; Qwen billed per actual usage (see table). Judge Sonnet 5.5 $2/$10.

## Method

1. Cloned `cmap_bake_5` (8 real sources, 97 chunks, 969 entities) to `cmap_s8_base`; own temporary FalkorDB container (removed after the run).
2. Built the graph and community reports ONCE with `anthropic/claude-haiku-5.5` (`run_project` + full `run_communities`: 416 level-0, 399 level-1, 1 company report; 54 qualifying findings with ≥2 sources). A first attempt was interrupted; the second run reused 134 stored reports. Harness-only change: open-question embeddings were cached in memory (production re-embeds every stored question on each insert, which made the run take >1 h — see follow-up).
3. Snapshotted `cmap_s8_base` into one DB per candidate; ran `run_recommend` per candidate on a fixed deterministic sample of 20 findings (5 company-level + 15 level-1, ordered by a hash of the finding text), unchanged prompt and code.
4. Recorded every model call (tokens, billed $, latency, raw content). JSON validity = the final answer per finding parses as JSON.
5. Judge graded the first 12 findings side-by-side (all six answers per call, blind letters, answers cut at 3,500 chars) on grounded / actionable / specific (non-vague, non-duplicative) / open_question (quality of the "data is incomplete" hypothesis). Quality = mean of the four × JSON-valid share.

## Results

| Model | Quality | Grounded | Actionable | Specific | Open question | JSON valid | Failed | Kept / dup-dropped | Latency med / p90 (s) | Tokens in / out | $ sample (20) | $ corpus (54) | $ 100x (5,400) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `deepseek/deepseek-v4.1-flash` | 0.758 | 0.80 | 0.81 | 0.71 | 0.72 | 20/20 | 0 | 11 / 9 | 23.1 / 45.0 | 58,647 / 94,708 | $0.0493 | $0.133 | $13.31 |
| `z-ai/glm-5.3-flash` | 0.760 | 0.72 | 0.76 | 0.75 | 0.81 | 20/20 | 0 | 11 / 9 | 7.5 / 11.2 | 44,431 / 28,819 | $0.0081 | $0.022 | $2.19 |
| `qwen/qwen3.8-27b` | 0.551 | 0.73 | 0.77 | 0.70 | 0.73 | 15/20 | 5 | 8 / 7 | 40.9 / 43.3 | 68,189 / 120,882 | $0.3085 | $0.833 | $83.30 |
| `openai/gpt-6-luna` | 0.797 | 0.84 | 0.81 | 0.76 | 0.78 | 20/20 | 0 | 14 / 6 | 13.8 / 17.9 | 44,831 / 29,005 | $0.0199 | $0.054 | $5.37 |
| `anthropic/claude-haiku-5.5` | 0.724 | 0.67 | 0.82 | 0.77 | 0.79 | 19/20 | 0 | 10 / 10 | 11.3 / 12.1 | 64,701 / 41,860 | $0.0271 | $0.073 | $7.32 |
| `meta/muse-spark-1.3-contributor` | 0.722 | 0.74 | 0.74 | 0.68 | 0.72 | 20/20 | 0 | 18 / 2 | 24.2 / 30.5 | 43,117 / 58,123 | $0.0156 | $0.042 | $4.21 |
Projection formula: `$ per finding = $ sample / 20`; corpus = × 54 qualifying findings; 100x corpus (~10,000 chunks) assumes findings scale linearly = × 5,400. Retries are included in the sample $.

Run costs (actual): shared report build ≈ $1.40 (second run $0.865 measured + interrupted first run estimated from its call count); six recommend runs $0.43; judge ≈ $0.55 (one judge pass was interrupted and rerun). Total ≈ $2.38.

## Example recommendations (first two stored per model; first option + experiment)

### `deepseek/deepseek-v4.1-flash`

1. **Problem:** The licensed-line product work record is scattered: policy assigns the Licensed Team to write Item Descriptions and request SKU cards from Carlos, but the reasons and details for that work often live outside ClickUp in Teams, emails, markups, NAS paths, PDFs, screenshots, costing tools, or memory. This causes context loss and forces work to be reconstructed even when a product card exists.
   - **First option:** Add a required rationale/source-link field to the ClickUp card for licensed-line SKU work, with the Licensed Team responsible for filling it before stage movement.
   - **Experiment:** For the next 10 licensed-line SKU cards, add a required 'rationale/source link' field in ClickUp before stage movement, and ask Carlos to include any item-level detail he already has. — *metric:* Count of cards with rationale/source link present and time spent per card reconstructing context from Teams, email, NAS, markups, PDFs, screenshots, costing tools, or memory. (the metric must be measured first)

2. **Problem:** Design revisions are not recorded in a single place for either POP or Spruce; feedback and change requests stay in messages, markups, and emails, so there is no audit trail of design changes.
   - **First option:** Create a lightweight shared revision log for both POP and Spruce, with a required one-line entry for each design change.
   - **Experiment:** Pilot a single shared revision log for one POP project and one Spruce project, requiring a one-line entry for each feedback or change request. — *metric:* Count of design changes with a log entry divided by total design changes found in messages, markups, and emails; also measure time to retrieve the latest approved revision. Baseline must be measured first.


### `z-ai/glm-5.3-flash`

1. **Problem:** The Licensed Team is responsible for item descriptions and SKU card work, but the reasons and details behind that work live outside ClickUp in Teams messages, emails, files, and people's memory, so a card shows the stage of work but not the context needed to act on it.
   - **First option:** Agree and document one designated place for item rationale (for example, a fixed field or comment section on each ClickUp card) and require that rationale be written there when work is done.
   - **Experiment:** For 30 days, ask the Licensed Team to record item rationale in one designated place on each ClickUp card (a fixed comment or field) as they work, with no other process changes. — *metric:* Count of ClickUp cards that contain item-level rationale versus cards completed with rationale reconstructed from Teams, email, or memory; the current rate must be measured first as a baseline since the DATA contains no numbers. (the metric must be measured first)

2. **Problem:** Design revisions in both POP and Spruce are recorded only in scattered messages, markups, and emails, so there is no single audit trail showing what changed, who requested it, or why.
   - **First option:** Designate a single shared location (e.g., a revisions log or card field in the existing workflow) for both POP and Spruce, and assign an owner role responsible for logging each design change request when it arrives.
   - **Experiment:** For 30 days, ask the Spruce side only to log every design change request in a single shared revisions list as it arrives, without changing any other step. — *metric:* Count of design change requests logged in the shared list versus change requests later found scattered in messages or emails; since the DATA contains no baseline numbers, measure the current share of unrecorded revisions first.


### `qwen/qwen3.8-27b`

1. **Problem:** The licensed-line work cards in ClickUp show stage but not the item-level reasons or details, so the written responsibility for item descriptions and SKU cards does not match where the working context actually lives. As a result, product cards can exist without enough context to act on them.
   - **First option:** Add a required short rationale field or comment to licensed-line ClickUp cards, with a simple template for reason, source link, and next action.
   - **Experiment:** For one licensed-line product card, require the Licensed Team to add a short rationale note and link to the primary source before moving the card to the next stage. — *metric:* Count the number of pilot cards that can be acted on without asking for missing context and time how long it takes to reconstruct context for a card; the baseline must be measured first because the data does not contain comparable numbers. (the metric must be measured first)

2. **Problem:** The Brand Assurance Form hand-off to Production is unclear because the written policy says a copy is sent to Production, while the described practice is that Production prints the form, and the data does not show whether the printed form is the same copy.
   - **First option:** Add one sentence to the responsibilities document stating whether Production prints the same copy that was sent or prints a separate copy for the boxes.
   - **Experiment:** For the next 30 days, add a reversible note to each Brand Assurance Form hand-off record saying whether the form was sent as a copy or printed by Production, and check whether the box has the form and trademark authorization. — *metric:* Count of shipping boxes with both the Brand Assurance Form and trademark authorization attached and a recorded copy type; the baseline count must be measured first. (the metric must be measured first)


### `openai/gpt-6-luna`

1. **Problem:** Licensed-line product cards often show a work stage without the rationale or detail needed to act, because that information is kept across other tools and people’s memory. This conflicts with the written responsibility for the Licensed Team to write item descriptions and request SKU cards from Carlos.
   - **First option:** Pilot a required context section on licensed-line ClickUp cards for the item rationale and a link to any supporting file or message. Keep detailed work in its existing tools, but make the card point to it.
   - **Experiment:** For 30 days, pilot a required rationale field and supporting-source link on a small, reversible batch of new licensed-line ClickUp cards; leave other cards and existing tools unchanged. — *metric:* Count cards in the pilot batch that lack usable rationale or a supporting-source link, and time how long it takes staff to locate the rationale; measure the same for a comparable baseline batch first. (the metric must be measured first)

2. **Problem:** Design revisions for POP and Spruce are scattered across messages, emails, and markups rather than kept in one audit trail. This makes it difficult to trace what changed and identify the current revision.
   - **First option:** Pilot a shared revision log for a small set of active projects, recording each requested change, its decision, and the current approved version.
   - **Experiment:** For 30 days, use a simple shared revision log on a small set of active projects in one line; record each change request, decision, date, and current approved version. Stop or revise the pilot if it disrupts work. — *metric:* Measure the number of change requests and how many are recorded in the log; also time how long it takes to find the latest approved revision. Establish these figures during the baseline period because the data provides no counts.


### `anthropic/claude-haiku-5.5`

1. **Problem:** Policy makes the Licensed Team responsible for Item Descriptions and for requesting SKU numbers and ClickUp cards from Carlos, but the working detail behind that work sits in Teams, email, Illustrator files, NAS paths, and people's memory. So a card shows the stage of the work but not the reasons for it.
   - **First option:** Add a required 'rationale location' field to the Licensed Team's ClickUp card template that links to where the reasons for the item are kept.
   - **Experiment:** For 30 days, add the 'rationale location' field to a sample of Licensed Team cards and ask the team to link the place where the reasons are kept, then remove the field if it does not help. — *metric:* Count how many times a team member has to look outside ClickUp to understand a card, and how many cards have a filled rationale location; this must be measured first because the DATA has no numbers. (the metric must be measured first)

2. **Problem:** The written policy says a copy of the Brand Assurance Form goes to Production, but Production actually prints its own form and attaches it to shipping boxes with the trademark authorization. Nobody can yet confirm that the printed form is the same one that was sent.
   - **First option:** Ask Production and the Licensed Team to confirm, step by step, which form is printed at shipping and where it comes from, then record the answer in the responsibilities document.
   - **Experiment:** For one set of shipments, have Production record which form version or copy was printed and attached, and compare it with the copy sent to Jamielynn and Production that week. — *metric:* Number of shipments where the attached form matches the sent copy, counted over the trial period, plus the count of mismatches found. (the metric must be measured first)


### `meta/muse-spark-1.3-contributor`

1. **Problem:** The Licensed Team is formally responsible for Item Descriptions and requesting SKU cards from Carlos, but the working detail behind that work often lives outside ClickUp, so written responsibility does not match where the actual record sits.
   - **First option:** Require the Licensed Team to add a link or path to the supporting detail location in each new ClickUp card when writing the Item Description.
   - **Experiment:** For new licensed-line items only, require the ClickUp card to include a link or path to where the supporting detail lives. — *metric:* Count share of new cards with a usable rationale link and time to locate context; baseline must be measured first. (the metric must be measured first)

2. **Problem:** Design revisions have no single audit trail. POP feedback stays in messages and markups and Spruce change requests stay in messages and emails.
   - **First option:** Require a short dated entry in one shared revision log for each design change, linked to the original message or markup.
   - **Experiment:** For a small set of active projects in one line, log every revision as a dated entry in one shared thread or document for 30 days. — *metric:* Count revisions with a dated log entry versus revisions found only in messages, markups, or emails; metric must be measured first to set a baseline.

## Reproducibility notes

- Databases on the test services host: `cmap_s8_base` (reports snapshot) and `cmap_s8_{deepseek,glm,qwen,gpt6luna,haiku,muse}` (one per candidate, each holds that model's stored recommendations).
- Harness scripts (session temp, not committed): wraps `brain.resolve.resolve._post_chat` to log usage/latency/content; samples candidates by patching `_candidates`; judge script sends one side-by-side prompt per finding.
- Haiku's 19/20: one answer was returned wrapped in prose/fences and was recovered by `brain/llm.py`, so it still produced a stored card.
- Follow-up found: `communities._store_open_questions` re-embeds every open question on each insert (3,544 questions → thousands of embedding calls); a production-scale run will be slow and costly until that is cached.
