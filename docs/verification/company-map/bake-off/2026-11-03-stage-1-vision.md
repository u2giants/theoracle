# Stage 1 — Vision transcription bake-off (2026-11-03)

Setting: `BRAIN_VISION_MODEL`. Code path: `apps/brain/brain/read/vision.py`, prompt
`apps/brain/brain/prompts/read_visual.md` (production prompt, unchanged), called
through `brain.llm.post_chat_with_rescue` at temperature 0 exactly as production does.
Run 11:42 AM – 11:50 AM EST. Machine-readable results: `2026-11-03-stage-1-vision.json`.

## Recommendation

- **Winner: `anthropic/claude-haiku-5.5`.** Every one of the 62 node labels and 14
  swimlanes on the real Edge Home flowchart copied verbatim, 64/67 reference arrows
  (95.5%), 10/11 arrow conditions, only 4 wrong arrows, and it was the only model that
  honestly reported clipped box text in `unreadable_regions`. About $0.005 per dense
  diagram.
- **Runner-up: `openai/gpt-6-luna`.** Close behind (81% arrows, 2 node labels missed at
  full size, 100% on a downscaled copy), slightly cheaper.
- **Incumbent `openai/gpt-4.1` fails the stage on the real flowchart**: it returned 64
  nodes but zero edges, and 23 of its labels are invented ("Meeting Assembly",
  "Jewelry versions", …). It only passes the small test fixture.

## Candidates and availability

All ids are Albert's verbatim list; all were present on OpenRouter `/api/v1/models`
on 2026-11-03 with image input. No substitutions.

| Model | Available | Price in / out per 1M tokens (OpenRouter, 2026-11-03) |
|---|---|---|
| google/gemini-3.8-flash | yes | $0.825 / $4.125 |
| openai/gpt-6-luna | yes | $0.10 / $0.50 |
| anthropic/claude-haiku-5.5 | yes | $0.10 / $0.50 |
| qwen/qwen2.5-vl-72b-instruct | yes | $0.80 / $1.00 |
| meta/muse-spark-1.3-contributor | yes | $0.10 / $0.20 |
| openai/gpt-4.1 (incumbent, reference) | yes | $2.00 / $8.00 |

## Instrument

1. **Real flowchart** — `Pop_Creations_Flow_12112025.png` ("Edge Home - Licensed Flow",
   6359×7610 px, 1.18 MB, sha256 prefix `d087b916f5e1f73d`), fetched read-only from the
   production storage bucket and sent at original size as production does.
2. **Text-poor SOP page** — `Licensing_Sheet_Automation_Workflow.pdf` page 2 (1 native
   character, so production routes it to vision), rendered at 150 dpi.
3. **Test fixture** — `apps/brain/tests/fixtures/licensing-approval-flowchart.png`
   against the recorded gold `tests/fixtures/recorded/vision_flowchart.json`.
4. Supplementary (not scored in the ranking): the real flowchart downscaled to
   2590×3100 px, run for Muse (which rejected the original) plus Haiku and Luna as controls.

One call per model per image (job brief §4.1 protocol).

### How the reference transcription was built

I read the flowchart image directly and wrote down every lane header (14), every box
label (62, including two boxes both labelled "Tech Pack Submit Authorization"), every
arrow-condition label (12), and 67 arrows I could trace end to end. I then compared all
six model outputs against it: wherever a model disagreed, I re-checked the drawing.
Arrows that are genuinely ambiguous on the drawing (the dashed fan-out from "Concept
Submit to Licensor", the "Before an Order" line that passes through "Files for Factory",
and a few overlapping connectors — 11 pairs) are accepted if returned but never
required and never counted as wrong. The reference
is stored in full under `reference` in the JSON file. The SOP page reference is its full
visible text, copied word for word.

### Metrics

- Node recall: reference labels matched by a returned label (normalized, ≥0.85 similarity).
- Verbatim: exact normalized match.
- Lane recall; edge recall (reference from→to pairs present); edge-condition recall.
- Wrong arrows: returned arrows not in the reference or the ambiguous set (a proxy for
  invented topology; spot-checked by hand for the top three — they are real misreads).
- Invented nodes: returned labels matching nothing on the page (<0.70 similarity).
- Text page: word recall and extra words vs the page text.
- Quality score 0–1 = 0.25 node recall + 0.25 edge recall + 0.10 lanes + 0.10 edge
  conditions + 0.15 fixture (node+edge)/2 + 0.15 text-page word recall − 0.01 per wrong
  arrow (capped at 10).

## Results

All six were valid JSON on every image except Muse on the real flowchart. All six
scored 100% on the fixture and 100% word recall with zero extra words on the SOP page,
so the real flowchart decides the ranking.

| Model | Quality | Nodes | Verbatim | Lanes | Edges | Edge cond. | Wrong arrows | Invented nodes | SOP words | Flow latency s | $ sample (3 calls) | $ corpus | $ 100× |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 0.940 | 1.000 | 1.000 | 1.000 | 0.955 | 0.909 | 4 | 0 | 1.0 | 30.2 | $0.0058 | $0.011 | $1.15 |
| openai/gpt-6-luna | 0.876 | 0.968 | 0.968 | 1.000 | 0.806 | 0.727 | 4 | 0 | 1.0 | 29.4 | $0.0029 | $0.008 | $0.82 |
| google/gemini-3.8-flash | 0.824 | 1.000 | 1.000 | 1.000 | 0.731 | 0.909 | 16 | 0 | 1.0 | 30.9 | $0.0281 | $0.076 | $7.57 |
| openai/gpt-4.1 (incumbent) | 0.494 | 0.403 | 0.306 | 0.929 | 0.000 | 0.000 | 0 (no edges) | 23 | 1.0 | 20.8 | $0.0270 | $0.069 | $6.85 |
| qwen/qwen2.5-vl-72b-instruct | 0.472 | 0.823 | 0.806 | 0.286 | 0.149 | 0.000 | 41 | 0 | 1.0 | 69.2 | $0.0142 | $0.044 | $4.39 |
| meta/muse-spark-1.3-contributor | 0.300 | fail | fail | fail | fail | fail | – | – | 1.0 | 0.3 (HTTP 400) | $0.0011 | $0.007* | $0.70* |

\* Muse cannot read the full-size image at all, so its projection only covers pages it can accept.

Tokens in/out (fixture / flowchart / SOP page): Haiku 2357/1088, 4994/8162, 2983/407;
Luna 2108/644, 10249/3497, 2410/315; Gemini 1281/1106, 1269/4874, 1291/832; GPT-4.1
1293/389, 953/1994, 953/220; Qwen 2249/418, 16577/3011, 2911/230; Muse 2277/1708, 0/0,
2799/1117. Dollar figures are OpenRouter's reported `usage.cost` per call.

Downscaled 2590×3100 copy (supplementary): Haiku nodes 1.00 / edges 0.881 / 4 wrong;
Luna nodes 1.00 / edges 0.851 / 4 wrong; Muse nodes 1.00 / edges 0.493 / 7 wrong.
Muse stays last on topology even when it can read the image.

### Failures and notes

- **Muse Spark 1.3 Contributor**: provider returned HTTP 400 "image decode limit exceeded"
  for the 6359×7610 PNG. Production sends originals, so this is a stage failure.
- **GPT-4.1**: zero edges and 23 invented labels on the real flowchart — the
  "prose/guess instead of transcription" pitfall from the job brief. Real wiring is lost.
- **Gemini 3.8 Flash**: reads every label but links boxes by position instead of following
  the arrows (16 wrong arrows), and costs ~6× Haiku.
- **Qwen 2.5 VL 72B**: misses most swimlanes, 41 wrong arrows, slowest (69 s).
- Haiku's 4 wrong arrows: Costing sheets elaboration→Upload to DFlow, Debriefing→Designs
  Approval, Concept Approved→Concept Approved w comments, Files for Factory→PPS Audit.

## Cost projection

Formula: `corpus $ = 1 × (dense-diagram call $) + 14 × (text-poor page call $)`. The
current corpus has 1 image and an estimated 14 sub-200-character PDF pages (7 counted
in the two SOP PDFs fetched; the other two SOP PDFs assumed similar). `100× $ = 100 ×
corpus $` (~1,500 vision calls at the planned ~10,000-chunk scale). Example, Haiku:
$0.00453 + 14 × $0.00050 = $0.0115 → $1.15 at 100×.

## Reproducibility

- Runner: production prompt + `post_chat_with_rescue`, temperature 0, 300 s timeout,
  model set per process; scorer is deterministic Python (no LLM judge needed for this stage).
- OpenRouter generation ids for every call are in the JSON (`generation_ids`).
- Spend this session: about $0.09 of the shared key (limit remaining was $24.22 before
  the run). No database, graph or production setting was touched; storage access was read-only.
