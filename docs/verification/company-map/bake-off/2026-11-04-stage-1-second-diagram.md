# Stage 1 vision: second dense real diagram (#363, 2026-11-04)

The stage 1 ranking rested on one dense real diagram (the Edge Home flowchart).
With Albert's approval (12:01 PM EST, relayed by the coordinator), a public
diagram was used **only as a test image**. It was kept in a scratch folder,
was not committed, and was never imported into the brain or any cmap database.

- **Image:** "BPMN Application to create a permit", by Arbeck, Wikimedia Commons,
  https://commons.wikimedia.org/wiki/File:BPMN_Application_to_create_a_permit.svg,
  license **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0). Rendered
  as the Wikimedia 3840×1045 PNG thumbnail.
- **Content:** a real BPMN process with 4 lanes or pools (Applicant, Platform,
  Other juridical agencies, Land Register), 24 flow objects (14 tasks, 5
  gateways, start and end events), 25 certain sequence arrows (7 labelled
  Yes/No/Submit), 5 text annotations, and dashed message flows. It is less
  dense than the Edge Home chart (62 boxes, 67 arrows) but has gateways, a loop
  back and cross-lane flows.
- **Method:** the same as stage 1. Each model got one call with the production
  `read_visual.md` prompt through `post_chat_with_rescue` at temperature 0.
  Scoring was deterministic: label match at ≥0.85 similarity, arrows mapped
  onto the reference, and wrong arrows counted. Message flows to the pools and
  the arrow from "Save or submit" to "Save" count as accepted-ambiguous.
  Annotations count as real text, not invented boxes. The reference and all
  scores are in
  [2026-11-04-stage-1-second-diagram.json](2026-11-04-stage-1-second-diagram.json).
  Quality is the mean of box recall, lane recall, arrow recall, arrow-label
  recall and (1 − wrong arrows ÷ 25).

| Model | Quality | Boxes | Arrows (of 25) | Arrow labels (of 7) | Wrong arrows | Time | Cost |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 (seat) | **1.00** | 24/24 verbatim | 25 | 7 | 0 | 22 s | $0.003 |
| meta/muse-spark-1.3-contributor | **1.00** | 24/24 verbatim | 25 | 7 | 0 | 38 s | $0.001 |
| google/gemini-3.8-flash | 0.98 | 24/24 | 24 | 7 | 1 | 17 s | $0.010 |
| openai/gpt-6-luna | 0.89 | 23/24 ("Set details" for "Get details") | 22 | 5 | 3 | 30 s | $0.002 |
| openai/gpt-4.1 (old seat) | 0.79 | 23/24 | 17 | 4 | 7 | 11 s | $0.014 |
| qwen/qwen2.5-vl-72b-instruct | 0.74 | 24/24 | 15 | 3 | 8 | 33 s | $0.006 |

## Findings

1. **The stage 1 pick holds.** Haiku 5.5 read this diagram perfectly as well,
   and it again reported uncertain areas honestly in `unreadable_regions`.
   It stays ahead of Luna, which dropped the label on the "Submit" end event and
   so lost the arrows around it.
2. **The bottom of the ranking holds too:** GPT-4.1 and Qwen again lose most of
   the arrows and labels.
3. **Muse is perfect on a normal-size image.** Its stage 1 failure came from
   the 6359×7610 image limit, not from reading ability. If the reader ever caps
   image size, Muse becomes a cheap fallback.
4. This diagram is easier than the Edge Home chart, because its layout is
   cleaner and it has fewer crossing arrows. The Edge Home chart is still the
   harder test, but the ranking now rests on two real diagrams.

Spend: about $0.04.
