---
summary: "Follow-up measurements of 2026-11-04 for the nine-stage bake-off: larger samples and repeat runs on cloned databases."
kind: proof
status: done
read-when: checking whether a bake-off result held on a larger sample
---

# Bake-off follow-ups (2026-11-04)

Follow-up measurements for the 2026-11-03 nine-stage bake-off, run on the test
services host on 2026-11-04 (from about 10:40 AM EST). Every database used was a
fresh `createdb -T` clone (`cmap_s366_*`, `cmap_s367_global`); `cmap_bake_*` and
`cmap_s8_base` were only used as templates. Code was `main` at `c6c906b1`
(includes #353 resolve rules, #344 and #365). Raw numbers are in the JSON files
named in each section.

## #368 — stage 9 grader: 30-item repeat stability

Method: the 45 distinct stored eval answers (`cmap.eval_run.results` in
`cmap_bake_1/2/3/5/6` and `cmap_s8_base`), sorted by stored score, 30 evenly
spaced items taken. Each item graded **3 times** by the production
`grade_answer` with the current `prompts/grade.md` (the PR #335 version), model
forced per process. 90 points per run (3 per item). Raw:
[2026-11-04-stage-9-grader-repeat.json](2026-11-04-stage-9-grader-repeat.json).

| Model | Items identical in all 3 runs | Run 1 = run 2 | Point labels stable | Median latency |
|---|---|---|---|---|
| openai/gpt-6-luna (current grade seat) | 24/30 (80%) | 29/30 | 84/90 (93%) | 3.6 s |
| anthropic/claude-sonnet-5.5 | **30/30** | 30/30 | **90/90** | 1.2 s |

Finding: **the dip is real for Luna and was noise for Sonnet.** Sonnet 5.5 is
fully repeatable at temperature 0 on 30 items. Luna changes at least one point
label on 1 item in 5 when graded three times: 4 flips covered ↔ missing on
hedged statements and 2 flips missing → contradicted (the old false-
contradiction pattern, now occasional rather than systematic). A single grading
pass with Luna therefore carries about ±1 point-label noise per 15 points; when
comparing two eval runs graded by Luna, differences under about 0.07 in mean
score should be treated as noise. This supports the stage 9 recommendation:
Sonnet 5.5 as the frozen grader for comparisons, Luna only where cost matters.
Spend: about $0.40.

## #364 — stage 2: 145 labelled alias pairs and rule-4/5 thresholds for voyage-4-lite

Method: 145 pairs (75 same-thing, 70 different-thing) built from the distinct
mention names in `cmap_s8_base` across 7 entity types (Customer 17, Department
25, Licensor 22, Person 25, Role 23, System 29, Vendor 4). Each pair was
labelled by reading the names and their quotes; the different-thing set is
deliberately hard (sister retailers, sibling roles, two licensors in one
sentence, look-alike servers). Two pairs were dropped as ambiguous (Mickey
Mouse/Disney and an identical-name pair). Each name was embedded with the
seated model `voyageai/voyage-4-lite` (1024 dims) twice: **as production does
it** (`surface — quote`, the mention embedding that rules 4 and 5 compare) and
**name only**. Raw pairs, labels and cosines:
[2026-11-04-stage-2-alias-pairs.json](2026-11-04-stage-2-alias-pairs.json).

| Embedding text | AUC (same vs different) | Recall at 0.92 | Wrong pairs at 0.92 | Recall at 0.80 | Wrong pairs at 0.80 |
|---|---|---|---|---|---|
| `surface — quote` (production) | **0.52** (chance) | 1% | 26% of different pairs | 9% | 30% |
| name only | **0.89** | 36% | **0** | 65% | 7% |

Findings:

1. **With the quote in the embedding, cosine says nothing about identity.**
   Two different things named in the same sentence score 0.98–0.99 (Concept
   Reviewers / Contract Reviewers, Sales / Production, Product Library /
   Master Data), while real aliases from different passages score 0.29–0.50.
   No threshold works: rule 4's 0.92 auto-merge would fuse about a quarter of
   the hard different-thing pairs and catch almost no real aliases. This is
   the mechanism behind the stage-5 fusions; #353 already routes the six
   name-like types to the judge, which removes the worst of it, but rule 4
   still applies to Step, Artifact, Process, System and other types, where
   the quote embedding scored 15% wrong pairs at 0.92.
2. **Re-fit thresholds on name-only voyage-4-lite cosine:**
   - Rule 4 (auto-assign): **0.88** is the lowest value with zero wrong
     pairs (highest different-thing pair: creative director / art director
     0.879); 0.92 keeps a safety margin and still catches 36% of aliases.
     Recommended: keep **0.92**, but on the name-only cosine.
   - Rule 5 (judge floor): **0.60** sends 92% of true aliases to the judge
     (0.55 → 97%) at the cost of about 40% of hard different pairs also going
     to the judge, which is what the judge is for. Recommended: **0.60**
     (down from 0.80).
3. The remaining misses below 0.60 are nicknames and code-to-name links
   (Liz / Elizabeth Parkin 0.47, Jen / Jennifer Chaffier, PPS / Pre-Production
   Sample). Rules 2b, 3 and the lexical candidate list already cover most of
   these; embedding cannot.

Consequence: the thresholds above only hold if rules 4/5 compare **name-only**
embeddings. Today `cmap.mention.embedding` and `cmap.entity.embedding` carry
the quote or description, so applying the new numbers needs a code change (a
name embedding per mention/entity or an on-the-fly name embed for the top
candidates). That change is filed as #399; until it lands, rule-4
auto-merge on the current embeddings should not be relied on. Spend: under
$0.01.

## #367 — stage 7: global mode on a clone with community reports

Method: `createdb -T cmap_s8_base cmap_s367_global` (`cmap_bake_5` plus Haiku
community reports: 416 L0, 399 L1, 1 L2), own FalkorDB container, graph
projected (969 nodes / 752 edges), answer model `anthropic/claude-haiku-5.5`
(the current answer seat). The same 20 questions were answered in
`mode="global"` and `mode="local"` with the production `answer_question`, then
judged by `anthropic/claude-sonnet-5.5` (five criteria 0–5, quality =
sum ÷ 25, hard fail = 0). Raw grades:
[2026-11-04-stage-7-global-mode.json](2026-11-04-stage-7-global-mode.json).

**The questions are still the drafts** in Appendix A of
`HANDOFF.d/2026-11-02T2057Z-edge-dev-mimo-model-overhaul-bakeoff-round2.md`:
the production `cmap.eval_question` table still holds only the five seed
questions, so the owner-final set does not exist yet. The rerun on final
questions stays open on #367.

| Mode | Quality | Hard fails | Correct | Synthesis | Honest | Citations valid | Readable | Sources cited (mean) | ≥3 sources | Median time | Median tokens / question | Model calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| local | **0.716** | 0 | 3.35 | 3.40 | 4.25 | 3.10 | 3.80 | 2.8 | 13/20 | 67 s | 85k | 1 |
| global | 0.588 | 1 (q19) | 2.79 | 3.37 | 4.00 | 2.53 | 2.79 | 6.6 | 19/20 | **434 s** | **526k** | 41 |

Findings:

1. **Global mode works end to end** on real reports: 19/20 answers, every one
   citing 3+ sources (mean 6.6), and the map-reduce path ran without errors
   except one question whose final reply was not valid JSON three times
   (Haiku wrapped it in a code fence or cut it; `answer response is not JSON`
   also hit 1 local call and 3 global calls that recovered on retry).
2. **Global is worse and far more expensive on these questions.** Quality
   0.59 vs 0.72, with lower correctness, citation validity and readability.
   It costs about 6× the tokens (≈$0.05–0.06 per question at Haiku prices
   against ≈$0.01) and about 7 minutes per answer, which is too slow for a
   chat reply.
3. Consequence for `auto` routing: sending broad questions to global mode
   makes answers slower and worse on this corpus. Until the reports improve
   or the global prompt is tuned, auto should prefer local; this is a
   product decision for the coordinator, filed on #367 rather than changed
   here.
4. Not re-measured: GLM-5.3-flash first-call empty rate (it is not seated).

Spend: about $1.5 for answers plus $0.49 judging.

## #366 — stages 4 and 5: larger judged samples

### Stage 4 (relations): Muse vs GLM-5.3, full corpus, 120 relations each

Method: two `createdb -T cmap_bake_5` clones with relations and relation
extraction rows removed, then the production `handle_relations` over all 8
sources (97 chunks) on `main` `c6c906b1`, which includes the #365 fix (8,000
output tokens, retry at 16,000). From each run 120 relations were sampled at
random (seed 366) and judged **twice** by `anthropic/claude-sonnet-5.5`,
grouped by passage. Raw:
[2026-11-04-stage-4-relations-larger-sample.json](2026-11-04-stage-4-relations-larger-sample.json).

| Model | Relations kept | Judged (pass 1 / 2) | Precision pass 1 | Pass 2 | Mean of both (95% CI) | Judge self-agreement | Wall time | Cost |
|---|---|---|---|---|---|---|---|---|
| meta/muse-spark-1.3-contributor | 1,120 | 72 / 72 | 0.85 | 0.92 | **0.89 ± 0.08** | 92% | 20 min | **$0.14** |
| z-ai/glm-5.3 | 1,336 | 59 / 70 | 0.86 | 0.87 | 0.85 ± 0.10 | 96% | 15 min | $0.47 |

The judge returned verdicts for about 60% of the sampled ids (it skipped ids
on passages with many relations), so about 70 relations per model were
graded, against 40 in the original stage. The confidence intervals still
overlap: **the larger sample confirms the tie on quality and does not reverse
the pick.** Muse stays the stage-4 seat on cost (≈3.4× cheaper) and
reliability; GLM-5.3 keeps 19% more relations and is faster. With the #365
budget both models finished every chunk with no failures. A gold set labelled
by a person remains the only way to separate them further; it is not worth it
while their precision is this close and Muse is cheaper.

### Stage 5 (resolve): Luna vs Muse after the #353 rule fix

Method: two `createdb -T cmap_bake_5` clones fully reset (decisions, aliases,
entities, `mention.entity_id`), then the production `run_resolve` on `main`
`c6c906b1`, which includes the #353 rules that send look-alike companies,
roles and people to the judge. Every judge **merge** plus 40 random
**rejections** (seed 5) were re-judged by `anthropic/claude-sonnet-5.5`. Raw:
[2026-11-04-stage-5-resolve-larger-sample.json](2026-11-04-stage-5-resolve-larger-sample.json).

| Model | Judge decisions | Merges | Merge precision | Rejection precision | Wall time | Cost |
|---|---|---|---|---|---|---|
| openai/gpt-6-luna (seat) | 1,808 (full corpus) | 127 | **0.91** (115/127) | 0.95 (38/40) | 42 min | $0.14 |
| meta/muse-spark-1.3-contributor | 655 (stopped at 870 of 2,077 mentions after 45 min) | 45 | 0.84 (38/45) | 0.93 (37/40) | — | — |

Findings:

1. **#353 made the judge matter.** The judge now decides 1,808 cases and 127
   merges on this corpus, against about 161 calls and 15 merges before, so
   the sample is 8× larger than in the original stage.
2. **Luna is confirmed as the stage-5 seat**: 0.91 merge precision over 127
   merges, cheap, and it finished. Muse was too slow to finish under the new
   rules (about 3× Luna's time for 40% of the corpus) and was not better on
   the part it finished. Some of the "false merges" counted against Luna are
   judge mistakes (jen → Jennifer Chaffier, POP → POP Creations, Senior
   Designer → Senior Designer are correct), so the true precision is
   slightly higher.
3. The remaining real false merges are vague single words absorbed into a
   longer entity (document, flow, line, months, presentation) — the same
   pattern as the original stage, and a candidate for a minimum-specificity
   rule rather than a model change.

Spend: about $0.14 resolve + ~$0.20 Muse partial + $0.43 / $0.15 judging.
