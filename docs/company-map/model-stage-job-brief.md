# THE ORACLE — Company Map model stages: job brief

**Written 2026-10-30, by MiMo on edge-dev, for Albert Hazan.**
Direction (Albert, 2026-10-30, from his chat): "the models chosen above were chosen
several model generations ago, you need to do a new bake-off for each stage." Plus
the standing direction from 2026-10-30: "cheaper non-Claude model for heavy work
(pick it with the step-11 eval) and a separate conversation model, Claude Haiku 5.5."
And: reorganize the model page so it lists the new stages of the Company Map
overhaul, better laid out, with less wasted white space.

**What this document is:** the job brief for picking models for every stage of the
Company Map pipeline (`apps/brain`), written in the same methodology as the old
role briefs in `apps/web/app/admin/settings/page.tsx` (the "Copy job brief"
strings): each stage described from the actual code — what it is fed, what it must
return, what separates a good model from a useless one — with a MEASURED BENCHMARK
and a HOW TO EVALUATE recipe that runs real inputs instead of abstract reasoning.
It also specifies the model-page rework and the bake-off protocol.

**Scope:** the nine model-touching stages of `apps/brain` (vision, embed, flat,
relations, resolve, community reports, answers, recommendations, eval grader).
The frozen legacy app (interview/extraction/synthesis routes) is out of scope
except that its admin controls must keep working.

---

## 1. The job

1. **Bake-off every stage against the current model catalog.** The seated models
   (`anthropic/claude-sonnet-4.5` for all reasoning, `openai/gpt-4.1` for vision,
   `openai/text-embedding-3-large` for embeddings) were chosen in the
   2026-06-era bake-offs and again for the step-9 live smoke. Several model
   generations have shipped since. Every stage gets measured competition.
2. **Heavy work goes to a cheap non-Claude model, chosen by the step-11 eval.**
   "Heavy" = the high-volume inference: relationship extraction, entity
   resolution, community reports (the cost center).
3. **Conversation gets its own model: Claude Haiku 5.5.** "Conversation" =
   question answering (local/global), interview text, recommendations — the
   human-facing prose.
4. **The model page lists the new stages**, organized for screen space, each with
   its job brief.

## 2. Methodology (how the old job briefs were written and how to use this one)

The old briefs (Vision, Interview, Extraction, Synthesis, … in
`apps/web/app/admin/settings/page.tsx`) share one method, and the extraction
bake-off of 2026-06 is its proof:

- **Judge candidates on real production-shaped input, not vibes.** The 2026-06
  bake-off fed a dense 14-lane swimlane transcription to every candidate; every
  model returned schema-valid JSON, yet claim recall varied ~10× (54 vs 5).
  "Fast + cheap + schema-clean" was the signature of the worst extractors.
- **One #1 criterion per stage, with the trap named.** For extraction it was
  recall on dense input. Each brief below names its own criterion and the way a
  bad model hides (under-extraction, over-merging, uncited prose, verdict drift).
- **HOW TO EVALUATE is a recipe, not an opinion:** feed the candidate the named
  input, check gates in the listed order, and only then look at price/latency.
- **Cost is a tiebreaker, never a filter**, until the quality gates pass.

This brief adds two rules the old world lacked:

- **Testing must equal production.** Whatever wins is what the Coolify env and any
  DB setting will run; eval runs record their model provenance
  (`cmap.eval_run.models`, PR #297) so a comparison is auditable. CI replays
  recorded fixtures and never judges model quality — the step-11 eval and the
  per-stage recipes below are the only model-quality instruments.
- **The grader never moves during a bake-off.** When candidates for answering are
  compared, the grade model is fixed (a strong model, currently
  `anthropic/claude-sonnet-4.5`) so scores are comparable. When the grader itself
  is being chosen, answers are frozen.

## 3. Stage inventory (from the code)

All chat calls go through OpenRouter (`https://openrouter.ai/api/v1`,
`temperature=0`). Model ids come only from env (`apps/brain/brain/config.py`);
no id is hard-coded. ScaleDown (`https://api.scaledown.xyz`) is the cheap
classification/extraction service with a frontier fallback. Every OpenRouter
chat call goes through `brain/llm.py:post_chat_with_rescue`: one retry with
doubled `max_tokens` and hidden low-effort reasoning when content comes back
empty (reasoning-flagged models can burn the budget on thinking — PR #307).

| # | Stage | Call site | Model slot | Volumes | JSON mode / max_tokens |
|---|-------|-----------|------------|---------|------------------------|
| 1 | Vision transcription | `brain/read/vision.py:65-105` (POST via `brain/llm.py`) | `BRAIN_VISION_MODEL` | 1 call per image / text-poor PDF page (<200 native chars) | plain chat (JSON-shaped prompt) |
| 2 | Embeddings | `brain/embed.py:51-92` | `BRAIN_EMBED_MODEL` (`BRAIN_EMBED_DIMS=1024`) | 64 texts/call; per chunk, mention, entity re-describe, question dedupe, paragraph resolve | /embeddings endpoint |
| 3 | Flat extraction | `brain/extract/flat.py:372-430` | ScaleDown + `BRAIN_FRONTIER_MODEL` fallback | 2 ScaleDown calls (classify+extract) or 1 frontier call per ~400-token chunk | fallback: plain chat |
| 4 | Relationship extraction | `brain/extract/relations.py:163-183,283-308` | `BRAIN_FRONTIER_MODEL` | 1 call per non-chatter chunk; ~100k calls on the full corpus (plan §11) | JSON mode, 2000 tokens |
| 5 | Entity resolution | `brain/resolve/resolve.py:103-125` | `BRAIN_FRONTIER_MODEL` | 1 judge call per ambiguous mention (cosine band 0.80–0.92, plus name-part/first-name collisions with >1 candidate regardless of band); 1 describe per entity ≥3 mentions | JSON mode, 4000 tokens |
| 6 | Community reports | `brain/graph/communities.py:256-278` (`_ask_report`) | `BRAIN_FRONTIER_MODEL` | 1 call per community (Leiden L0/L1 + 1 company report); 6 workers; 12k-token contexts; reuse on rerun | JSON mode, 4000 tokens |
| 7 | Question answering | `brain/answer/answer.py:96-117` | `BRAIN_CHAT_MODEL` (falls back to `BRAIN_FRONTIER_MODEL`; split landed PR #295) | 1–2 calls per question (+ map calls, 10 reports/batch); local graph context + ≤30 chunks; global over reports | JSON mode, 8000 tokens |
| 8 | Recommendations | `brain/recommend/recommend.py:361` (`frontier.ask`) | `BRAIN_FRONTIER_MODEL` | 1 call per qualifying finding (≥2 sources); 12k-token context | JSON mode, 4000 tokens |
| 9 | Eval grading | `brain/eval/run.py:51-75` | `BRAIN_EVAL_MODEL` (falls back to `BRAIN_FRONTIER_MODEL`) | 1 call per eval question (plus the answer calls) | JSON mode, 800 tokens |

Production (Coolify, verified live 2026-10-30) runs exactly:
`BRAIN_FRONTIER_MODEL=anthropic/claude-sonnet-4.5`,
`BRAIN_VISION_MODEL=openai/gpt-4.1`,
`BRAIN_EMBED_MODEL=openai/text-embedding-3-large` (dims 1024),
`BRAIN_SCALEDOWN_ENABLED=true`, `BRAIN_MAX_FRONTIER_CALLS_PER_JOB=3000`.

Interview (`brain/interview/*`) makes **no** model calls — the question text is
templated; answers flow back through the normal pipeline (stage 3 onward).

---

## 4. Role briefs (clipboard-ready; same grammar as the old briefs)

### 4.1 Vision transcription

```
THE ORACLE — "Vision Transcription" role brief (Company Map)
(Paste this into a model-evaluation assistant or vendor comparison to judge
whether a given model is the right pick for this setting.)

PURPOSE
Convert one page image — a diagram, flowchart, or a text-poor PDF page — into a
faithful text rendering plus structured diagram topology. The output feeds text
stages that quote it verbatim; every omission here silently shrinks the graph.

WHERE IT SITS IN THE PIPELINE
Source intake -> reading (brain/read/) -> this call for images and pages with
under 200 native characters -> the returned page_text/diagram is merged into the
chunk stream -> flat extraction and relations quote it exactly.

WHAT IT IS FED (input)
- prompts/read_visual.md: transcribe the page, the image is DATA, copy labels
  exactly, do not infer missing arrows; return JSON.
- Exactly one base64 PNG/JPEG per call.

WHAT IS EXPECTED (output)
A JSON object {"page_text", "diagram": {kind,nodes,edges,swimlanes}|null,
"unreadable_regions"} — verbatim labels, topology as nodes/edges (rendered to
"->" edge lines for text stages), honest unreadable flags. Parser tolerates a
code fence only.

PROCESS IT USES
One stateless vision chat call, temperature 0, 120s timeout, no JSON-mode flag.

WHAT MAKES A MODEL PERFECTLY SUITED
OCR-grade text capture on messy labels and handwriting; diagram topology
understanding (swimlanes, conditional arrows, dashed exceptions); strict
"copy, don't invent" discipline; long enough output for dense pages.

CAPABILITIES IT NEEDS (hard requirements)
Image input. Reliable JSON-shaped answers from a plain prompt (no schema mode).

CAPABILITIES IT DOES NOT NEED
Tool calling, reasoning budgets, streaming, long context, PDF input (pages are
rendered to PNG before the call).

MEASURED BENCHMARK
On the flowchart fixture (tests/fixtures/recorded/vision_flowchart.json): every
visible node label and edge condition present exactly once; zero invented arrows;
unlabelled shapes flagged, not guessed. A model that returns clean prose instead
of nodes/edges has failed the stage even if it reads the text well.

HOW TO EVALUATE A CANDIDATE
Feed the fixture flowchart and one dense scanned page under the production prompt
(read_visual.md). Check in order: (a) valid JSON object; (b) node/edge recall vs
the gold fixture; (c) verbatim labels (substring match); (d) no invented edges;
(e) then cost/latency. One call per candidate is enough to rank.

KNOWN PITFALLS
1. Prose summarization instead of transcription — the graph then cannot quote
   labels.
2. Image-generation or "image editing" models presented as vision readers.
3. Truncated output on dense pages (cut-off JSON is discarded by the parser).

BOTTOM LINE
Pick the cheapest vision model with the best dense-diagram transcription and
verbatim discipline. Current seat: openai/gpt-4.1. Compete it against current
vision tiers (including cheaper flash/lite vision models) on the two-fixture
test above; the winner must be no worse on node/edge recall.
```

### 4.2 Embeddings

```
THE ORACLE — "Embeddings" role brief (Company Map)

PURPOSE
Turn chunk texts, mention strings, entity descriptions and questions into
vectors for retrieval, dedupe and the cosine bands that gate entity resolution.

WHERE IT SITS IN THE PIPELINE
Every stage that compares text: local answering (top-8 entity retrieval, passage
selection), resolve rules 4-5 (rule 4 auto-merges at cosine ≥0.92; rule 5
judges the 0.80–0.92 band), open-
question dedupe, recommendation dedupe, global citation resolution.

WHAT IT IS FED (input)
Batches of 64 raw texts. Vectors requested at exactly 1024 dims
(BRAIN_EMBED_DIMS — text-embedding-3-large defaults to 3072 and is explicitly
downsized).

WHAT IS EXPECTED (output)
One float vector per input, exactly `dims` floats, order preserved. Anything
else raises and is retried 3×.

PROCESS IT USES
POST /embeddings on OpenRouter, batched, counted as embedding_tokens.

WHAT MAKES A MODEL PERFECTLY SUITED
Deterministic vectors; strong short-business-text similarity (titles, roles,
system names); stable dimensionality support; cheap per token (this is the
highest-call-count stage).

CAPABILITIES IT NEEDS (hard)
Custom output dimensions (or exactly 1024 native); batch endpoint; exact
dimensionality contract.

CAPABILITIES IT DOES NOT NEED
Everything else — reasoning, JSON, tools, vision.

MEASURED BENCHMARK
The resolve banding is the real test: on the fixture corpora the same-entity
pairs must sit ≥0.92 (auto-merge band) and the judged pairs inside 0.80–0.92;
different-entity pairs under 0.80. Also: per-chunk embedding cost under the
current seat's.

HOW TO EVALUATE A CANDIDATE
Re-embed the fixture mention set with the candidate; recompute the cosine
matrix; measure band placement against the entity labels in the fixture gold
(tests/test_resolve.py scenarios). Then compare $/1M tokens. This stage is
purely measurable — no judgment call.

KNOWN PITFALLS
1. Dimensionality drift (3072 vs 1024) silently breaking stored vectors —
   re-embed the whole corpus when switching, never mix.
2. Models whose similarity collapses on short name strings ("Jessica",
   "Artwork Log") even when document similarity looks fine.

BOTTOM LINE
This is the most commoditized stage: pick on band accuracy + price. Current
seat: openai/text-embedding-3-large @1024. Compete it against current cheap
embedding tiers (and any new provider offerings); switch only with a full
re-embed plan. Low priority in the bake-off — measurable, cheap, and a switch
costs a corpus rebuild.
```

### 4.3 Flat extraction (passage classification + entity pickup)

```
THE ORACLE — "Flat Extraction" role brief (Company Map)

PURPOSE
Classify each chunk into one of 7 passage kinds (process, responsibility, rule,
reference, complaint, decision, chatter) and lift flat entities (16 types) with
exact character spans. This is the cheap bulk pass; by call count it is the
majority of all model work.

WHERE IT SITS IN THE PIPELINE
Reading/chunking (≈400-token windows) -> this pass per chunk -> mentions feed
relations and entity resolution. Chunks classified "chatter" at score ≥0.8 are
skipped by later stages — a misclassification here drops knowledge silently.

WHAT IT IS FED (input)
Primary path: ScaleDown /classify (7 label rubrics) and /extract (16 entity
rubrics) with the chunk text. Fallback path: prompts/flat_extract.md asking a
frontier model for the same rubrics in one JSON answer (both stages cached in
one call).

WHAT IS EXPECTED (output)
classify {"top_label","scores"}; extract entities[] {text,type,confidence,
start,end}. Mentions survive only with valid type, confidence ≥0.5 and a
locatable span (exact offsets → substring → casefold repair); the quote is the
containing sentence.

PROCESS IT USES
ScaleDown HTTP API (x-api-key), 3 attempts then frontier fallback
(BRAIN_SCALEDOWN_ENABLED=false forces the fallback). 8 threads per source.

WHAT MAKES A MODEL PERFECTLY SUITED
High recall on entities in noisy business text (people, roles, systems,
documents, metrics); calibrated confidence (the 0.5 cut is meaningless if the
model is miscalibrated); exact span copying; honest classification (chatter
detection is load-bearing).

CAPABILITIES IT NEEDS (hard)
JSON answers; span-exact copying; cheap per call (this is the volume).

CAPABILITIES IT DOES NOT NEED
Reasoning, long context (one chunk at a time), tools, conversation.

MEASURED BENCHMARK
On the fixture set (transcript + procedure PDF + flowchart text, gold in
tests/fixtures/recorded/scaledown/*.json): mention recall ≥95% of gold spans;
chatter precision: no process/rule chunk ever classified chatter ≥0.8;
confidence calibration: accepted mentions dominate rejected ones in gold
precision.

HOW TO EVALUATE A CANDIDATE
Run the three fixture chunks through the candidate with the production rubrics.
Check in order: (a) valid JSON both passes; (b) mention recall vs gold; (c)
span exactness (substring of chunk); (d) chatter false-skips; (e) then price.
The frontier-fallback candidate must be evaluated with prompts/flat_extract.md
exactly as production runs it.

KNOWN PITFALLS
1. High-confidence shallow extraction (few entities, all obvious) — recall is
   the headline, same trap as the old extraction brief.
2. Paraphrased spans — the quote-sentence logic needs locatable text.
3. Note the ScaleDown fallback is a different shape (one call vs two) — a
   cheap frontier model here also serves the fallback when ScaleDown is off.

BOTTOM LINE
ScaleDown already owns the primary path; this stage's bake-off is really about
the frontier fallback model (which must not be worse than the old
claude-sonnet-4.5 fallback on recall) and about keeping chatter detection
honest. Cheap non-Claude candidates belong here.
```

### 4.4 Relationship extraction — HEAVY

```
THE ORACLE — "Relationship Extraction" role brief (Company Map)
(Read "#1 CRITERION" and "HOW TO EVALUATE" before forming an opinion.)

PURPOSE
Link the mentions step 3 found in a chunk into typed relationships — what hands
off to what, what depends on what, what is an exception — plus pick up mentions
step 3 missed. This is the highest-volume reasoning stage (~1 call per chunk;
plan §11 budgets ~100k calls on the full corpus) and the backbone of the graph.

WHERE IT SITS IN THE PIPELINE
Flat extraction -> this call per chunk (mentions keyed m1..mN, previous chunk's
last 2 sentences as context) -> relations + new mentions -> entity resolution ->
graph projection. Whatever it fails to emit is missing from the map.

WHAT IT IS FED (input)
prompts/relations.md with {{mentions_json}}, {{previous_context}},
{{chunk_text}}. Ontology: 14 relation types, 4 stances.

WHAT IS EXPECTED (output)
{"relations":[{from,to,type,description,stance,confidence,quote}],
"new_mentions":[{key,type,name,quote}]} — every quote an EXACT substring of the
chunk (validator drops otherwise), types/stances in ontology, keys resolvable;
inferred links capped at confidence 0.6.

PROCESS IT USES
OpenRouter chat, temperature 0, JSON mode, max_tokens 2000, 180s timeout,
3 attempts/chunk, 8 threads, per-job frontier cap, resumable per chunk.
Truncation is salvaged item-wise (_complete_items) but every dropped relation is
lost graph.

WHAT MAKES A MODEL PERFECTLY SUITED (priority order)
1. RELATION RECALL on dense process chunks (the extraction brief's lesson, one
   level up: a "valid JSON + 3 relations" model is under-extracting).
2. Type discipline — conditional/exception/stance fidelity, not everything
   flattened to "depends_on".
3. Verbatim quote copying (validator-enforced).
4. Strict JSON reliability at 2000 tokens; a truncating model silently loses
   tail relations.
5. THEN cost — this stage alone can dominate the run's token bill.

CAPABILITIES IT NEEDS (hard)
JSON mode (or equivalent strict JSON); exact-quote copying; enough output
budget to emit every relation in a dense chunk.

CAPABILITIES IT DOES NOT NEED
Vision (chunks carry text), tools, streaming, long context (one chunk + hints).

MEASURED BENCHMARK
On the fixture chunk set (gold = tests/fixtures/recorded/frontier/relations.json
and the smoke's 546-edge corpus): relation recall ≥90% of gold edges; zero
invalid-type rows; ≥95% quotes exact substrings; type variety (at least the
conditional/exception kinds appear when the source has them); truncation rate
<2% of chunks.

HOW TO EVALUATE A CANDIDATE
Feed the fixture chunks with gold mentions under prompts/relations.md. Check in
order: (a) valid JSON; (b) relation RECALL vs gold (headline); (c) type/stance
fidelity; (d) quote exactness; (e) truncation frequency; (f) only then $/1M and
tokens per chunk. Then run the end-to-end step-11 eval with the graph the
candidate built (bake-off protocol §5).

KNOWN PITFALLS
1. The extraction trap one level up: schema-valid, quote-valid, and shallow.
   Output-token volume on a dense chunk is a red-flag detector — ~1-2k tokens
   means it gave up early.
2. Loose "tool-call" JSON from providers without true JSON mode — malformed
   fields fail validation and the chunk yields nothing.
3. Fabricated quotes (the validator drops them — the relation vanishes).

BOTTOM LINE
This is where the cheap non-Claude seat is most valuable and most risky: the
bake-off must PROVE recall parity on real chunks before the switch. Current
seat: anthropic/claude-sonnet-4.5. Compete current-generation non-Claude
candidates (and cheap Claude) on the recipe; winner goes to production only if
its fixture recall passes and its step-11 end-to-end mean holds.
```

### 4.5 Entity resolution (judge + describe) — HEAVY-ADJACENT

```
THE ORACLE — "Entity Resolution" role brief (Company Map)

PURPOSE
Two judgment calls: (1) judge whether a mention is the same real-world thing as
a candidate entity ("Jessica" vs "Jessica Martinez" — but NOT two different
process steps with similar names); (2) write a factual canonical description
from quotes for entities with ≥3 mentions.

WHERE IT SITS IN THE PIPELINE
After relations. Deterministic rules 1-4 (alias, exact, name-part, cosine
≥0.92) absorb the easy merges; the judge runs ONLY on the ambiguous cosine band
[0.80, 0.92) and first-name collisions, on up to 5 candidates with sample
quotes. Verdicts persist (cmap.resolve_decision); describes feed community
reports and answering.

WHAT IT IS FED (input)
Judge: prompts/resolve_judge.md — mention {name,type,quote,source_title} + 5
candidates (canonical name, description, 2 quotes). Describe:
prompts/entity_describe.md — type, all names, up to 12 distinct quotes.

WHAT IS EXPECTED (output)
Judge: {"same_as": id|null,"confidence","reason"} — applied only at confidence
≥0.7; "if unsure, null" is the prompt rule. Describe:
{"canonical_name","description"} — "using only the quotes"; truncated JSON is
salvaged field-wise.

PROCESS IT USES
JSON mode, temperature 0, max_tokens 4000, 3 attempts; job frontier cap.

WHAT MAKES A MODEL PERFECTLY SUITED
Conservative identity judgment (over-merging is the worst failure — it fuses
two process steps into one entity and corrupts every downstream report);
cautious null returns; quote-grounded description writing; strict JSON.

CAPABILITIES IT NEEDS (hard)
JSON mode; careful comparative judgment across short texts.

CAPABILITIES IT DOES NOT NEED
Long context (candidates are compact), tools, streaming.

MEASURED BENCHMARK
From the resolve fixtures (tests/test_resolve.py scenarios + recorded smoke):
same-entity pairs accepted at ≥95% recall in the judge band; different-entity
pairs merged in <2% of cases (precision is the headline); descriptions cite no
fact absent from the quotes (spot-check 100% on fixture).

HOW TO EVALUATE A CANDIDATE
Replay the fixture mention/candidate pairs (the judge-band cases especially)
under prompts/resolve_judge.md. Check in order: (a) valid JSON; (b) merge
PRECISION (no false merges — this ranks before recall); (c) recall on true
pairs; (d) description faithfulness; (e) then cost. A model that confidently
merges near-miss names is disqualified regardless of everything else.

KNOWN PITFALLS
1. Over-merging similar names (two "Mike"s, two "approval" steps).
2. Chatty verdicts that break the JSON contract (truncation on long reasons).
3. Descriptions that read the quotes too freely and invent roles/dates.

BOTTOM LINE
Lower volume than relations but higher blast radius per error. Candidate cheap
non-Claude models must PROVE merge precision; if none do, this stage stays on
a stronger model even if relations moves. Current seat:
anthropic/claude-sonnet-4.5.
```

### 4.6 Community reports — HEAVY (cost center) and human-read

```
THE ORACLE — "Community Reports" role brief (Company Map)

PURPOSE
Write the map itself: per Leiden community a briefing (title, 120-200 word
summary, 5-12 findings with source_ids, open questions), rolled up L1 -> the
company report with "Top 10 cross-department issues". These texts ARE what
Albert and Ilona read, and what global answers are built on.

WHERE IT SITS IN THE PIPELINE
Graph projection -> Leiden (seed=0, deterministic) -> one call per community ->
stored reports reused on rerun (keyed level+entity set) -> answering (global),
recommendations, the /map UI.

WHAT IT IS FED (input)
prompts/community_report.md with a fitted context (12k-token budget): L0 =
entity list + top 40 edges + ≤25 quotes with source ids; L1/L2 = child reports'
summaries+findings.

WHAT IS EXPECTED (output)
{"title","summary","findings":[{text,kind,stance,entity_ids,source_ids}],
"open_questions":[str]}; findings with no real source_id are dropped. The
prompt rule: "Do not invent numbers. Every finding must list at least one
source_id."

PROCESS IT USES
JSON mode, temperature 0, max_tokens 4000, 6 parallel workers, one retry then
skip (never kill the pass), job cap.

WHAT MAKES A MODEL PERFECTLY SUITED
Grounded synthesis (findings traceable to source_ids — enforced, but weak
models cite decoratively); compression of noisy cross-department evidence into
clear prose; policy-vs-practice judgment; no invented metrics; decent writing
(Albert reads this).

CAPABILITIES IT NEEDS (hard)
JSON mode at 4000 tokens; long-context synthesis within 12k tokens.

CAPABILITIES IT DOES NOT NEED
Tools, streaming, vision.

MEASURED BENCHMARK
On the fixture corpus (smoke's 230-report run) and the real corpus run of
2026-10-30 (330 L0 communities): ≥95% findings carry valid source_ids;
zero invented numbers when inputs contain none; summary length in band; and
the step-11 global questions score at parity with the incumbent
(mean ≥ incumbent − 0.05). Coverage check: the top-5 fixture themes (licensing
stall, artwork hand-off, ...) each appear in some finding.

HOW TO EVALUATE A CANDIDATE
Two steps. (a) Report-quality: give the candidate the same fitted context the
production call uses for 3 representative communities (one clean, one noisy,
one cross-department); grade with a fixed strong grader on: source_id validity,
theme coverage, invented-number absence, summary clarity (the grader rubric
lives in the bake-off harness, not the grade.md eval prompt). (b) End-to-end:
build the reports with the candidate and run the step-11 global questions.
The candidate passes only if both hold.

KNOWN PITFALLS
1. Decorative citations — findings that name source_ids loosely or fabricate
   them (the filter drops some, but not all).
2. Beautiful empty prose — well-written summaries that miss the themes; read
   3 reports against the fixture gold before believing a score.
3. Cost blowups: this is the cost center (up to 12k-token contexts, hundreds
   of calls). A mid-quality model at 1/5 the price can be the right pick ONLY
   if (a) and (b) hold.

BOTTOM LINE
The hardest slot to price-optimize because it is both the volume center and
the reading surface. Albert's rule: the step-11 eval decides. If a cheap
candidate holds end-to-end parity, take it; if it lands between cheap-heavy
and premium-conversation in quality, this stage can take the conversation
model (Claude Haiku 5.5) as a middle seat. Current seat:
anthropic/claude-sonnet-4.5 (provisional until this bake-off).
```

### 4.7 Question answering (conversation)

```
THE ORACLE — "Question Answering" role brief (Company Map)

PURPOSE
Answer employee/admin questions against the map — the voice of The Oracle.
Local mode: graph neighbourhood + retrieved passages with verbatim quote
citations. Global mode: synthesis over community reports. This is
human-facing conversation; tone and honesty matter alongside grounding.

WHERE IT SITS IN THE PIPELINE
The /map/ask UI and Teams interviews -> routing (ScaleDown classify) -> local
answer (top-8 entities, depth-2 neighbourhood, ≤30 chunks, quotes JSON) and/or
global answer (reports, map-reduce in batches of 10 when >60k tokens) ->
citation validation (quotes must be exact substrings; invalid citations dropped
and sentences marked "(uncited)") -> the answer + citations back to the UI.

WHAT IT IS FED (input)
prompts/answer_local.md / answer_global.md / answer_map.md with history (6
turns), the question, graph context, passages (ScaleDown-compressed when >6k
tokens) and a QUOTES list with chunk_ids. The persona: "Operations Oracle" —
investigative, cites, flags unknowns.

WHAT IS EXPECTED (output)
{"answer_md" (every factual sentence ends [n]), "citations":[...],
"unknowns":[]} — quotes copied EXACTLY from the QUOTES list. Invalid JSON is
fence/comma/salvage tolerant.

PROCESS IT USES
JSON mode, temperature 0, max_tokens 8000, 3 attempts. The user is waiting —
this is the one stage where latency is felt.

WHAT MAKES A MODEL PERFECTLY SUITED
Verbatim quote copying (citation validation is unforgiving); grounding honesty
("unknowns" over invention); stance/nuance reading (policy vs practice);
natural concise prose (Albert and Ilona read these); reliable JSON at 8000
tokens; decent latency.

CAPABILITIES IT NEEDS (hard)
JSON mode; strong instruction-following on citation markers; 12k+ context.

CAPABILITIES IT DOES NOT NEED
Vision (text contexts), tools, giant output caps.

MEASURED BENCHMARK
The step-11 eval IS this stage's benchmark: mean score over the eval questions
(currently 5 fixture seeds; the 20 real questions when Albert and Ilona write
them), citation validity rate (drop rate), and the cross-source questions
("Where does licensing approval stall and why?") answered with sources. Also:
median latency per question.

HOW TO EVALUATE A CANDIDATE
Run the step-11 eval on the same graph with the candidate as answer model and
a FIXED grader (see §2). Check in order: (a) valid JSON + citation drop rate;
(b) eval mean (parity or better than incumbent − 0.05); (c) the stall question
reads correctly; (d) latency; (e) price. This is Albert's designated
conversation seat: Claude Haiku 5.5 is the standing assignment — the eval
proves or revises it.

KNOWN PITFALLS
1. Paraphrased quotes — citations vanish, sentences become "(uncited)", score
   collapses. Fastest quality test there is.
2. Confidently merged stances (the "policy vs practice" distinction is the
   product).
3. Long-windedness — answer length past the marker discipline.

BOTTOM LINE
Assigned seat: Claude Haiku 5.5 (Albert's direction, 2026-10-30). Prove it on
the step-11 eval against 1-2 challengers; if it lands materially below the
incumbent on citation validity or mean, report back before switching. Cost
marginal (low volume); quality is the whole game.
```

### 4.8 Recommendations (conversation-adjacent)

```
THE ORACLE — "Recommendations" role brief (Company Map)

PURPOSE
For each bottleneck/complaint/contradiction finding with ≥2 sources: one
structured recommendation — the problem, 2-4 COMPETING explanations (one must
be "the data is incomplete"), 3-5 options (one must be "No change"), and a
reversible experiment with a metric. Quantified claims are scrubbed in code
when the evidence has no numbers.

WHERE IT SITS IN THE PIPELINE
After communities. Finding + quotes + area report (12k fitted) -> this call ->
cmap.recommendation rows -> the /map/recommendations page (Accept/Reject/
Running/Measured).

WHAT IT IS FED (input)
prompts/recommend.md with finding, ≤20 quotes, source list, community report.

WHAT IS EXPECTED (output)
{"problem","explanations","options","experiment","duplicate_of"} — code
enforces shape, injects the missing "incomplete data" / "No change" items,
scrubs percentage/money patterns to "an unmeasured amount", and drops problems
the model marks `duplicate_of` an earlier one (PR #299) before the cosine
dedupe gate.

PROCESS IT USES
JSON mode, temperature 0, max_tokens 4000, 1 call per qualifying finding.

WHAT MAKES A MODEL PERFECTLY SUITED
Genuine competing-hypothesis thinking (the product's signature); restraint on
numbers; practical reversible-experiment design; tight problem statements
(they feed embedding dedupe).

CAPABILITIES IT NEEDS (hard)
JSON mode; judgment quality in hypothesis/experiment generation.

CAPABILITIES IT DOES NOT NEED
Long context, tools, streaming.

MEASURED BENCHMARK
Fixture gate (tests/test_recommend.py): the licensing-stall fixture yields a
recommendation with ≥2 explanations incl. "incomplete data", a "No change"
option, no digit-percent pattern when inputs have numbers. Plus human read of
3 real-corpus recommendations for plausibility (this output goes to Albert).

HOW TO EVALUATE A CANDIDATE
Run the fixture finding + 2 real-corpus findings through the candidate under
prompts/recommend.md. Check: (a) valid JSON with the mandated items; (b) no
invented numbers; (c) explanation quality (mutually distinct, evidence-linked);
(d) experiment sanity (reversible, measurable, has an owner role); (e) price.

KNOWN PITFALLS
1. Invented savings ("reduce cycle time by 30%") — code scrubs some patterns
   but the model should not generate them.
2. One-sided advocacy — the competing-explanations structure is the point.
3. Dedupe-hostile problem statements (near-duplicate recommendations).

BOTTOM LINE
Low volume, high visibility. This can ride the conversation seat (Claude
Haiku 5.5) if it passes (c)/(d); it must NOT ride a candidate that writes
confident invented numbers. Current seat: anthropic/claude-sonnet-4.5.
```

### 4.9 Eval grading (the instrument)

```
THE ORACLE — "Eval Grading" role brief (Company Map)

PURPOSE
Score an answer against the question's expected points: {"covered","missing",
"contradicted"} indexes. Score = covered/total − 0.2 per contradiction. This
model is the BAKE-OFF INSTRUMENT — its consistency is what makes every other
comparison meaningful.

WHERE IT SITS IN THE PIPELINE
Step-11 eval: per question, after answering. prompts/grade.md carries the
question, numbered expected points, and the answer.

WHAT IT IS FED (input)
Question + 3-6 expected points + the answer markdown.

WHAT IS EXPECTED (output)
Index lists only; contradicted wins over covered; every unlisted point counts
missing. "Covered" requires a citation marker in the sentence.

PROCESS IT USES
JSON mode, temperature 0, max_tokens 800, 3 attempts.

WHAT MAKES A MODEL PERFECTLY SUITED
Semantic equivalence judgment (paraphrase counts); consistency across runs
(temperature 0 is not a guarantee); strict index discipline; no generosity
bias (an answer that says something different is NOT covered).

CAPABILITIES IT NEEDS (hard)
JSON mode; careful reading; consistency.

CAPABILITIES IT DOES NOT NEED
Long context (answers are short), creativity, speed.

MEASURED BENCHMARK
Agreement with the keyword-grader fixture expectations
(tests/test_eval_fixture.py) ≥0.8 mean on the seed set; self-consistency:
two runs of the same input give identical indexes.

HOW TO EVALUATE A CANDIDATE
Grade the same 5 fixture answers twice with the candidate; require identical
indexes both runs and agreement with the fixture expectations. Then — and only
then — it may replace the incumbent grader, AFTER a bake-off cycle completes
(never mid-cycle).

KNOWN PITFALLS
1. Generosity drift — score inflation that makes every candidate look equal.
2. Mid-cycle grader swaps — invalidates every comparison in flight.

BOTTOM LINE
During the whole bake-off the grader is FROZEN on anthropic/claude-sonnet-4.5
(current seat). Grader candidates are evaluated at the very end and switched
only between cycles. This stage is about trust, not cost (1 call/question).
```

---

## 5. Bake-off protocol

**Candidate selection.** Pull the live OpenRouter catalog at run time
(`GET https://openrouter.ai/api/v1/models` — never trust a list written months
ago). Shortlist per stage by: (a) chat models priced under the incumbent's
input price for heavy stages (any price for conversation — the seat is
assigned); (b) capability fit from §4's "NEEDS"; (c) at most 4 candidates per
stage incl. the incumbent. Known-generation candidates to expect at 2026-10-30
and worth checking first: current Gemini flash tiers, current GPT mini tiers,
DeepSeek v4 tiers, Qwen 3.x, GLM 5.x, Kimi/MiniMax/StepFun current flags —
plus `anthropic/claude-haiku-5.5` for the conversation seat.

**Known candidate failures already measured (2026-10-30, edge-dev3 session;
detail in `HANDOFF.d/2026-10-30T1442Z-edge-dev3-claude-step14-model-split.md`
§4):** `deepseek/deepseek-v4.1-flash` and `qwen/qwen3.8-flash` crash the
relations stage with "frontier relations message content is not text" —
reasoning-flagged models burn `max_tokens` on thinking and return empty
content in JSON mode; treat empty content as a stage failure and prefer
non-reasoning tiers for the JSON stages (or raise max_tokens and retest).
`anthropic/claude-haiku-5.5` returned empty content on 2 of 5 eval answers —
must be fixed before it takes the conversation seat. Two eval scores recorded
that day (0.47 / 0.40) came from an empty graph and are INVALID.
A rescue now exists at every OpenRouter call site (`brain/llm.py`): one retry
with doubled max_tokens and hidden low-effort reasoning when content comes
back empty. A second empty response is still a stage failure.

**Order of runs (cheapest evidence first).**
1. **Per-stage micro-evals** (§4 recipes) on fixture inputs — hours, dollars.
2. **Stage swap + step-11 eval** on the real corpus (seed questions now; the
   20 real questions when written): rebuild the affected stage's outputs, run
   `evaluate`, compare means. **The grader stays frozen.** Each eval run's
   `models` manifest (PR #297) is the record.
3. **Everything at once**: the winning configuration gets one full smoke
   (`python -m brain.smoke --live`) + one eval run; those numbers go in the PR.

**Budget rules.** The shared OpenRouter key caps at $25/day (it stalled a
workday on 2026-10-29). Spend order: micro-evals (sub-dollar per candidate)
→ step-11 runs (the5-seed eval is ~10 calls + answers). Real-corpus graph
rebuilds are the expensive ones (relations ≈ 1 call/chunk) — do them one stage
at a time, after the micro-eval pass, and only for finalists. Run heavy smokes
right after the midnight-UTC reset.

**Provenance.** Every eval run records `models` (answer, grade, vision, embed,
scaledown flag, extraction model counts). The results table below is filled
from those rows — no number enters it without an eval_run id or a micro-eval
output file under `docs/verification/company-map/bake-off/`.

**Results table (to fill during the bake-off):**

| Stage | Incumbent | Candidates | Fixture result | Step-11 mean | Winner | Evidence |
|-------|-----------|------------|----------------|--------------|--------|----------|
| 1 Vision | openai/gpt-4.1 | | | n/a | | |
| 2 Embeddings | openai/text-embedding-3-large | | | n/a | | |
| 3 Flat fallback | claude-sonnet-4.5 | | | | | |
| 4 Relations | claude-sonnet-4.5 | | | | | |
| 5 Resolve | claude-sonnet-4.5 | | | | | |
| 6 Community reports | claude-sonnet-4.5 | | | | | |
| 7 Answers (conversation) | → claude-haiku-5.5 | | | | | |
| 8 Recommendations | claude-sonnet-4.5 | | | | | |
| 9 Grader (frozen) | claude-sonnet-4.5 | | | | | |

## 6. Model page rework spec

**Goal:** the admin model surface (today `apps/web/app/admin/settings/page.tsx`
role cards + `apps/web/app/admin/settings/model-pool/` checkbox grid) becomes a
page that (a) lists the NEW Company Map stages as its primary content, (b) is
compact — no `max-w-2xl` half-empty columns, no duplicated filter headers, no
23-column checkbox sparsity, (c) carries each stage's role brief (§4) behind a
"Copy job brief" button, and (d) keeps the legacy app's model controls working
in one collapsed section (the old app still runs; do not delete its settings).

**Layout.**
- Page header: title + one-line explanation + a link to this brief.
- **New stages block** (primary): a responsive 2-column card grid (single
  column under `md`) — one card per §3 stage, ordered by pipeline position.
  Each card: stage title + one-line role + the current model id (`font-mono
  text-xs`) + the stage's seat status (chips: incumbent / assigned / bake-off
  pending / frozen grader) + its env-var name and the note "set in Coolify app oracle-brain" +
  "Copy job brief" button. Card padding `px-4 py-3`, `gap-3`; no
  legend boxes repeated per card — one page-level legend.
- **Model pool block** (secondary): the provider×model matrix is legacy
  machinery (its `model_pool_*` columns feed the legacy pickers) — keep its
  behavior, label it "Legacy application model pools", and fix its layout:
  wrap the tables in an `overflow-auto` scroll container, use ONE sticky filter header for all
  provider tables instead of repeating it per table, and keep the route
  `/admin/settings/model-pool` working.
- **Legacy block** (bottom, collapsed by default): the existing
  interview/extraction/synthesis/aux cards, unchanged behavior.
- Max width `max-w-5xl` (not `max-w-2xl`, not full-bleed) — this is the
  "less wasted white space" fix; cards get useful density instead of a
  left-aligned 672px column.

**Config source for the new stage rows (architecture).**
The plan locks "no hard-coded model ids in code. Env only" (plan §11), and the
Coolify env is where the seats live today (verified 2026-10-30). So the page
does not invent a second config store: a small brain endpoint `GET /models`
(service token, mirrors the `eval_run.models` manifest) feeds the cards the
live env values, each card names its env var (e.g. `BRAIN_FRONTIER_MODEL`) and
the card says where it is set (Coolify app `oracle-brain`). Seating a bake-off
winner = the AI operator updates that env. The model split landed in PR #295:
`BRAIN_CHAT_MODEL` for the conversation seat, `BRAIN_EVAL_MODEL` for the
frozen grader, `BRAIN_FRONTIER_MODEL` for heavy work — each falls back to the
frontier model when unset. If the bake-off later proves we change models often
enough to deserve DB-backed seats, that is a separate, explicitly approved
change — not smuggled in with the layout.

**Job-brief wiring.** The §4 texts become the page's clipboard briefs: each
stage card copies its brief through the clipboard API
(`navigator.clipboard.writeText` in `company-map-stages.tsx`), one per new
stage card. Keep the §4 texts and the page copy in sync when a fact changes.

## 7. Decisions this brief locks

1. Conversation seat = **Claude Haiku 5.5** (Albert's words, 2026-10-30),
   proven on the step-11 eval before it ships to production.
2. Heavy stages (relations, resolve, reports) go to the best cheap non-Claude
   candidate **only** where the §4 gates and the step-11 eval hold; the
   community-reports slot may end up on the conversation model instead — the
   eval decides.
3. The eval grader is frozen during the bake-off.
4. Testing equals production: fixture micro-evals use the production prompts
   verbatim; eval runs record model provenance (PR #297); the winner's exact
   config is what the Coolify env receives.
5. The model page lists the new stages first; legacy controls survive in a
   collapsed section.

