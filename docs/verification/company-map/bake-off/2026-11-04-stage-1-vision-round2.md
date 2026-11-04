# Stage 1 vision bake-off, round 2 (2026-11-04)

Albert asked at 4:30 PM EST: "do a new bake-off for diagram reading." This file
is the full re-run: 7 diagrams, 10 candidate models, and the production prompt.
Raw scores and references are in
[2026-11-04-stage-1-vision-round2.json](2026-11-04-stage-1-vision-round2.json).
The run took place on the test services host between about 4:40 and 5:30 PM EST.
Production was not touched: T6 was rebuilding it. The vision stage reads only
the image, so no database or FalkorDB was involved.

## Recommendation

- **Seat: `anthropic/claude-sonnet-5.5`.** It is the best on every diagram
  type (mean 0.99). It is the best on our own Edge Home flowchart (61/67
  arrows, 11/11 conditions, 4 wrong arrows). It gave **identical output on all
  3 repeats** of that chart and both repeats of the org chart, and it invented
  no box labels. It costs about $0.07 per dense diagram and $0.01–0.03 per
  simpler page, against about $0.004 for Haiku. Diagrams are rare in the
  corpus (1 image so far), so even 100 dense diagrams cost about $7.
- **No per-type routing is needed** with Sonnet seated.
- **Budget alternative: keep `anthropic/claude-haiku-5.5`, but route org
  charts away from it.** Haiku is second-best on the Edge Home flowchart but
  unstable on org charts: across three runs it found 11, 5 and 30 of 30
  reporting lines. If Haiku stays, send org charts to `openai/gpt-6-luna`
  (28/30 on both runs). Luna is also the steadiest cheap all-rounder (mean
  0.97, $0.014 for all 7 images).
- **Not usable as the seat:** GPT-6.1 Terra and Muse 1.3 both fail with an HTTP
  400 "image too large" error on the 6359×7610 company original, which
  production sends unresized. Both are perfect on every normal-size image. If
  the reader ever caps image size, Muse becomes the cheapest strong option.
  GPT-4.1 (the old seat), Qwen 2.5 VL and Nemotron 3.5 VL lose most arrows.

This is the coordinator's and Albert's call: no seat was changed here.

## Test set

| Key | Diagram | Kind | Source and license | Reference |
|---|---|---|---|---|
| edge | Edge Home "Licensed Flow" (company corpus) | 14-lane swimlane flowchart, 6359×7610 | read-only from production storage | 62 boxes, 67 arrows, 11 conditions |
| permit | BPMN Application to create a permit | BPMN process | [Commons](https://commons.wikimedia.org/wiki/File:BPMN_Application_to_create_a_permit.svg), CC BY 4.0, Arbeck | 24 / 25 / 7 |
| audit | Merge Request Acceptance | 3-lane BPMN swimlane map | [Commons](https://commons.wikimedia.org/wiki/File:Audit-flow.svg), CC0, Foundation for Public Code | 15 / 18 / 5 (paths through unlabelled gateways contracted) |
| dhs | DHS Organizational Chart 2023 | org chart | [Commons](https://commons.wikimedia.org/wiki/File:DHS_Organizational_Chart_2023.png), public domain, U.S. DHS | 31 boxes / 30 lines, undirected |
| network | Screened Subnet Firewall | scanned network diagram | [Commons](https://commons.wikimedia.org/wiki/File:Screened_Subnet_Firewall.png), public domain, Wack & Carnahan (NIST) | 4 labelled devices |
| gantt | Neutral Buoyancy Simulator Gantt, March 1967 | scanned table-like schedule | [Commons](https://commons.wikimedia.org/wiki/File:Neutral_Buoyancy_Simulator_Gantt_chart_March_1967.png), public domain, NASA | 11 task rows |
| whiteboard | A "Two Way" Whiteboard at Newhouse III | photo of a hand-drawn schema | [Commons](https://commons.wikimedia.org/wiki/File:A_%27Two_Way%27_Whiteboard_at_Newhouse_III_(2035894088).jpg), CC BY 2.0, Vin Crosbie | 9 legible handwritten labels |

The public images were used only as test files. They were kept in a scratch
folder, not committed, and never imported into the brain or any cmap database.

## Scoring

Scoring is deterministic and uses no LLM judge.

- **Boxes:** a returned box counts when its label matches a reference label at
  ≥0.85 similarity (or by containment).
- **Arrows:** returned arrows are mapped onto reference boxes. Paths through
  unlabelled gateways or events are contracted. An arrow counts as **found** if
  it is in the reference, and **wrong** if it is neither in the reference nor
  an accepted-ambiguous arrow.
- **Invented:** a returned label that is not on the image (not a box, lane,
  condition, annotation or page text).
- **Text-only images** (network, gantt, whiteboard) score boxes found anywhere
  in the box labels or `page_text`.
- **Per-image quality** is the mean of box recall, arrow recall,
  (1 − wrong ÷ reference arrows), condition recall and (1 − invented ÷
  boxes). A failed call scores 0.
- **Cost and time** come from OpenRouter `usage.cost` and wall time.

### Quality per diagram (first run)

| Model | Mean | Edge Home flowchart | Permit BPMN | Audit swimlane | DHS org chart | Network | Gantt (scan) | Whiteboard photo | $ for 7 images | Seconds for 7 |
|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5.5 | **0.991** | 0.96 | 1.00 | 0.97 | 1.00 | 1.00 | 1.00 | 1.00 | 0.2008 | 83 |
| google/gemini-3.8-flash | **0.976** | 0.85 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0780 | 137 |
| openai/gpt-6-luna | **0.966** | 0.89 | 0.92 | 0.97 | 0.98 | 1.00 | 1.00 | 1.00 | 0.0141 | 150 |
| minimax/minimax-m3.1-flash | **0.957** | 0.80 | 0.89 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0512 | 318 |
| anthropic/claude-haiku-5.5 | **0.951** | 0.92 | 0.95 | 1.00 | 0.79 | 1.00 | 1.00 | 1.00 | 0.0109 | 64 |
| nvidia/nemotron-3.5-super-vl | **0.863** | 0.58 | 0.74 | 0.92 | 0.80 | 1.00 | 1.00 | 1.00 | 0.0189 | 89 |
| openai/gpt-6.1-terra | **0.857** | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0851 | 100 |
| meta/muse-spark-1.3-contributor | **0.857** | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0061 | 149 |
| openai/gpt-4.1 | **0.755** | 0.00 | 0.86 | 0.87 | 0.67 | 1.00 | 1.00 | 0.89 | 0.3258 | 319 |
| qwen/qwen2.5-vl-72b-instruct | **0.714** | 0.48 | 0.66 | 0.71 | 0.68 | 1.00 | 0.95 | 0.50 | 0.0555 | 248 |

### Repeat stability (2 extra runs for the top seats)

| Model | Edge Home arrows found / wrong (3 runs) | DHS lines found (runs) |
|---|---|---|
| anthropic/claude-sonnet-5.5 | 61/4, 61/4, 61/4 | 30, 30 |
| anthropic/claude-haiku-5.5 | 57/8, 61/4, 58/7 | 5, 30 (11 in the earlier test) |
| openai/gpt-6-luna | 55/4, 55/12, 56/4 | 28, 28 (28 in the earlier test) |

All three found 59 of the 62 Edge Home boxes. The 3 misses are the same
clipped labels for every model. Under this scorer's stricter fuzzy match,
Haiku's earlier 62/62 is 59/62.

### Findings

1. **Our own flowchart is the only test that still separates the strong
   models.** All ten read the Gantt chart, the network labels and the legible
   whiteboard words. All except Qwen and GPT-4.1 read every box on the
   BPMN and org-chart images. The differences are in arrows.
2. **Run-to-run variance is real for Haiku and Luna even at temperature 0.**
   A single run is not enough to rank close models. Sonnet was the only fully
   repeatable model.
3. **Transparent images are a production hazard.** Sent as-is (transparent
   background, black lines), the network diagram looked "entirely black" to
   Luna, Gemini, Minimax, Terra, Muse and GPT-4.1, and they returned nothing.
   Haiku, Sonnet, Nemotron and Qwen read it. The table above uses a copy
   flattened to white. **The reader should flatten transparency to white
   before sending.** This is a small code fix, separate from the seat choice.
4. **Invented labels were rare.** Sonnet named two unlabelled gateways on
   the audit map ("Parallel gateway …"). No other model invented a label on any
   image.
5. **Size limits:** Muse ("image decode limit exceeded") and GPT-6.1 Terra
   ("requires 47362 patches") reject the 6359×7610 original. GPT-4.1 returned
   no usable JSON on it.

Spend for this round: about $1.40 including repeats. OpenRouter
limit_remaining was $19.42 before the run and $17.52 after (other sessions were spending in parallel).

## Appendix: every score (first run)

| Model | Diagram | Boxes found | Arrows found | Wrong arrows | Arrow labels | Invented labels | Seconds | $ |
|---|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5.5 | edge | 59/62 | 61/67 | 4 | 11/11 | 0 | 30.8 | 0.0674 |
| anthropic/claude-sonnet-5.5 | permit | 24/24 | 25/25 | 0 | 7/7 | 0 | 9.8 | 0.0234 |
| anthropic/claude-sonnet-5.5 | audit | 15/15 | 18/18 | 0 | 5/5 | 2 | 9.5 | 0.0254 |
| anthropic/claude-sonnet-5.5 | dhs | 31/31 | 30/30 | 0 | — | 0 | 10.8 | 0.0298 |
| anthropic/claude-sonnet-5.5 | network_white | 4/4 | — | — | — | 0 | 5.3 | 0.0136 |
| anthropic/claude-sonnet-5.5 | gantt | 11/11 | — | — | — | 0 | 9.7 | 0.0261 |
| anthropic/claude-sonnet-5.5 | whiteboard | 9/9 | — | — | — | 0 | 6.9 | 0.0151 |
| google/gemini-3.8-flash | edge | 59/62 | 47/67 | 16 | 9/11 | 0 | 27.0 | 0.0194 |
| google/gemini-3.8-flash | permit | 24/24 | 24/25 | 1 | 7/7 | 0 | 18.3 | 0.0103 |
| google/gemini-3.8-flash | audit | 15/15 | 18/18 | 0 | 5/5 | 0 | 30.4 | 0.0157 |
| google/gemini-3.8-flash | dhs | 31/31 | 30/30 | 0 | — | 0 | 25.4 | 0.0148 |
| google/gemini-3.8-flash | network_white | 4/4 | — | — | — | 0 | 11.7 | 0.0049 |
| google/gemini-3.8-flash | gantt | 11/11 | — | — | — | 0 | 15.0 | 0.0078 |
| google/gemini-3.8-flash | whiteboard | 9/9 | — | — | — | 0 | 9.6 | 0.0050 |
| openai/gpt-6-luna | edge | 59/62 | 55/67 | 4 | 8/11 | 0 | 21.2 | 0.0030 |
| openai/gpt-6-luna | permit | 23/24 | 22/25 | 2 | 6/7 | 0 | 31.9 | 0.0023 |
| openai/gpt-6-luna | audit | 15/15 | 17/18 | 2 | 5/5 | 0 | 31.0 | 0.0029 |
| openai/gpt-6-luna | dhs | 31/31 | 28/30 | 0 | — | 0 | 22.3 | 0.0013 |
| openai/gpt-6-luna | network_white | 4/4 | — | — | — | 0 | 8.6 | 0.0010 |
| openai/gpt-6-luna | gantt | 11/11 | — | — | — | 0 | 18.8 | 0.0021 |
| openai/gpt-6-luna | whiteboard | 9/9 | — | — | — | 0 | 15.8 | 0.0015 |
| minimax/minimax-m3.1-flash | edge | 59/62 | 44/67 | 22 | 8/11 | 0 | 113.3 | 0.0187 |
| minimax/minimax-m3.1-flash | permit | 23/24 | 22/25 | 2 | 5/7 | 0 | 73.5 | 0.0088 |
| minimax/minimax-m3.1-flash | audit | 15/15 | 18/18 | 0 | 5/5 | 0 | 45.2 | 0.0071 |
| minimax/minimax-m3.1-flash | dhs | 31/31 | 30/30 | 0 | — | 0 | 20.5 | 0.0046 |
| minimax/minimax-m3.1-flash | network_white | 4/4 | — | — | — | 0 | 24.6 | 0.0041 |
| minimax/minimax-m3.1-flash | gantt | 11/11 | — | — | — | 0 | 16.5 | 0.0037 |
| minimax/minimax-m3.1-flash | whiteboard | 9/9 | — | — | — | 0 | 24.3 | 0.0042 |
| anthropic/claude-haiku-5.5 | edge | 59/62 | 57/67 | 8 | 10/11 | 0 | 22.0 | 0.0035 |
| anthropic/claude-haiku-5.5 | permit | 24/24 | 24/25 | 2 | 6/7 | 0 | 8.5 | 0.0014 |
| anthropic/claude-haiku-5.5 | audit | 15/15 | 18/18 | 0 | 5/5 | 0 | 11.6 | 0.0020 |
| anthropic/claude-haiku-5.5 | dhs | 31/31 | 5/30 | 0 | — | 0 | 6.6 | 0.0014 |
| anthropic/claude-haiku-5.5 | network_white | 4/4 | — | — | — | 0 | 2.2 | 0.0004 |
| anthropic/claude-haiku-5.5 | gantt | 11/11 | — | — | — | 0 | 7.5 | 0.0014 |
| anthropic/claude-haiku-5.5 | whiteboard | 9/9 | — | — | — | 0 | 5.7 | 0.0009 |
| nvidia/nemotron-3.5-super-vl | edge | 55/62 | 0/67 | 0 | 0/11 | 0 | 27.9 | 0.0042 |
| nvidia/nemotron-3.5-super-vl | permit | 24/24 | 15/25 | 8 | 3/7 | 0 | 12.6 | 0.0043 |
| nvidia/nemotron-3.5-super-vl | audit | 14/15 | 13/18 | 1 | 5/5 | 0 | 15.1 | 0.0026 |
| nvidia/nemotron-3.5-super-vl | dhs | 31/31 | 11/30 | 5 | — | 0 | 8.8 | 0.0034 |
| nvidia/nemotron-3.5-super-vl | network_white | 4/4 | — | — | — | 0 | 5.1 | 0.0011 |
| nvidia/nemotron-3.5-super-vl | gantt | 11/11 | — | — | — | 0 | 11.1 | 0.0020 |
| nvidia/nemotron-3.5-super-vl | whiteboard | 9/9 | — | — | — | 0 | 8.2 | 0.0013 |
| openai/gpt-6.1-terra | edge | fail: image too large (400) | | | | | 5.5 | |
| openai/gpt-6.1-terra | permit | 24/24 | 25/25 | 0 | 7/7 | 0 | 21.8 | 0.0148 |
| openai/gpt-6.1-terra | audit | 15/15 | 18/18 | 0 | 5/5 | 0 | 18.9 | 0.0225 |
| openai/gpt-6.1-terra | dhs | 31/31 | 30/30 | 0 | — | 0 | 22.3 | 0.0151 |
| openai/gpt-6.1-terra | network_white | 4/4 | — | — | — | 0 | 5.3 | 0.0047 |
| openai/gpt-6.1-terra | gantt | 11/11 | — | — | — | 0 | 14.2 | 0.0162 |
| openai/gpt-6.1-terra | whiteboard | 9/9 | — | — | — | 0 | 12.0 | 0.0118 |
| meta/muse-spark-1.3-contributor | edge | fail: image too large (400) | | | | | 0.8 | |
| meta/muse-spark-1.3-contributor | permit | 24/24 | 25/25 | 0 | 7/7 | 0 | 44.5 | 0.0015 |
| meta/muse-spark-1.3-contributor | audit | 15/15 | 18/18 | 0 | 5/5 | 0 | 26.0 | 0.0012 |
| meta/muse-spark-1.3-contributor | dhs | 31/31 | 30/30 | 0 | — | 0 | 22.0 | 0.0011 |
| meta/muse-spark-1.3-contributor | network_white | 4/4 | — | — | — | 0 | 18.4 | 0.0006 |
| meta/muse-spark-1.3-contributor | gantt | 11/11 | — | — | — | 0 | 18.3 | 0.0009 |
| meta/muse-spark-1.3-contributor | whiteboard | 9/9 | — | — | — | 0 | 18.6 | 0.0007 |
| openai/gpt-4.1 | edge | fail: no JSON | | | | | 273.1 | |
| openai/gpt-4.1 | permit | 23/24 | 20/25 | 4 | 5/7 | 0 | 7.8 | 0.0141 |
| openai/gpt-4.1 | audit | 15/15 | 11/18 | 5 | 5/5 | 0 | 10.7 | 0.0142 |
| openai/gpt-4.1 | dhs | 31/31 | 10/30 | 20 | — | 0 | 9.3 | 0.0146 |
| openai/gpt-4.1 | network_white | 4/4 | — | — | — | 0 | 3.8 | 0.0055 |
| openai/gpt-4.1 | gantt | 11/11 | — | — | — | 0 | 6.5 | 0.0089 |
| openai/gpt-4.1 | whiteboard | 7/9 | — | — | — | 0 | 7.6 | 0.0071 |
| qwen/qwen2.5-vl-72b-instruct | edge | 51/62 | 10/67 | 38 | 0/11 | 0 | 92.5 | 0.0164 |
| qwen/qwen2.5-vl-72b-instruct | permit | 23/24 | 11/25 | 9 | 2/7 | 0 | 43.2 | 0.0055 |
| qwen/qwen2.5-vl-72b-instruct | audit | 15/15 | 10/18 | 0 | 0/5 | 0 | 33.1 | 0.0116 |
| qwen/qwen2.5-vl-72b-instruct | dhs | 31/31 | 11/30 | 19 | — | 0 | 53.4 | 0.0056 |
| qwen/qwen2.5-vl-72b-instruct | network_white | 4/4 | — | — | — | 0 | 6.0 | 0.0023 |
| qwen/qwen2.5-vl-72b-instruct | gantt | 10/11 | — | — | — | 0 | 15.2 | 0.0079 |
| qwen/qwen2.5-vl-72b-instruct | whiteboard | 0/9 | — | — | — | 0 | 4.9 | 0.0062 |
