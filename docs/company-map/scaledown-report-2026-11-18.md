---
summary: "ScaleDown analysis of 2026-11-18: where small task-specific models can cut the cost of the brain, written ahead of bulk Teams, ClickUp and email intake for the two project managers."
kind: reference
status: current
read-when: plan_pm_message_intake.md cites the cost analysis, or someone asks which brain calls could move to ScaleDown
---

> Correction (2026-11-18, after access probes): the Graph app also holds chat-read permission; only mailbox read is missing. See plan_pm_message_intake.md STATUS row A.

# ScaleDown Migration Plan — oracle

> Generated: 2026-11-18T19:49:18.784Z
> Report version: 1

## Current AI Architecture

All model use lives in the Python brain (apps/brain). Chat calls go through one helper (brain/llm.py post_chat_with_rescue) to OpenRouter with model ids taken from per-stage seats; ScaleDown is called directly over HTTP. A source is read into ~400-token passages; each passage is classified by ScaleDown /classify (already live) and chatter >= 0.8 is skipped; a seated cheap chat model extracts named things (ScaleDown /extract is the fallback path); then ONE chat call per non-chatter passage extracts typed relations with verbatim quotes - the cost centre. Later stages (entity resolution, community reports, recommendations, answers, grading) run per entity, community or question rather than per passage. Answers already compress retrieved context with ScaleDown /compress/raw/. There is no batch path and no intake for email, Teams chat history or ClickUp today; the Graph app holds User.Read.All only.

Usage patterns: (1) passage classification - ScaleDown, flat.py - already migrated; (2) flat extraction - seated chat model with ScaleDown fallback, flat.py; (3) relation extraction - seated chat model, relations.py - cost centre; (4) source dating - flat seat, dates.py; (5) interview message judges - chat model, interview/*.py; (6) entity resolution judge - resolve.py; (7) community reports, recommendations, answers, grading - chat models, keep; (8) answer context compression - ScaleDown, already migrated.

Planned new pattern (not in code yet): bulk intake of two project managers' email, Teams messages and ClickUp records. Design intent: free rule-based cleaning and thread assembly first, then a ScaleDown thread-level relevance gate and summary, then the existing passage pipeline with relation extraction on the cheapest chat model that passes a labelled quality gate, batched.

| Usage Pattern | Provider | Files | Purpose |
|---|---|---|---|
| Passage classification | scaledown | `apps/brain/brain/extract/flat.py` | Label each passage; skip chatter. Already on ScaleDown. |
| Flat extraction | openrouter (seated chat model), scaledown fallback | `apps/brain/brain/extract/flat.py` | Named things with types from each non-chatter passage. |
| Relation extraction (cost centre) | openrouter | `apps/brain/brain/extract/relations.py` | One call per non-chatter passage: typed, quoted relations between known mentions. |
| Source dating | openrouter (flat seat) | `apps/brain/brain/read/dates.py` | Find the date a source was written. |
| Interview message judges | openrouter | `apps/brain/brain/interview/inbound.py`, `apps/brain/brain/interview/profile.py`, `apps/brain/brain/interview/followup.py`, `apps/brain/brain/interview/tick.py` | Short label and wording judgements on Teams replies. |
| Entity resolution judge | openrouter | `apps/brain/brain/resolve/resolve.py` | Decide whether two mentions are the same thing; describe entities. |
| Reports, recommendations, answers, grading | openrouter | `apps/brain/brain/graph/communities.py`, `apps/brain/brain/recommend/recommend.py`, `apps/brain/brain/answer/answer.py`, `apps/brain/brain/eval/run.py` | Open-ended synthesis and answering; stays on chat models. |
| Answer context compression | scaledown | `apps/brain/brain/answer/answer.py` | Compress retrieved context before answering. Already on ScaleDown. |
| Planned: bulk email / Teams / ClickUp intake | scaledown + cheapest passing chat model (batched) |  | Not in code yet. Rule-based cleaning, thread-level ScaleDown gate and summary, then the passage pipeline. |

## Summary

| Metric | Value |
|---|---|
| Files scanned | 236 |
| Files with AI API calls | 5 |
| Total integration opportunities | 6 |
| Providers detected | openrouter (httpx, OpenAI-compatible) |

### Call Complexity Breakdown

| Complexity | Count |
|---|---|
| highly_complex | 1 |
| simple | 2 |
| trivial | 1 |
| moderate | 1 |

## 1. Replace Classification Calls with `sd_classify`

**Estimated savings: ~95% per call**

| File | Line | Complexity | Confidence |
|---|---|---|---|
| `apps/brain/brain/extract/relations.py` | 231 | highly_complex (5/5) | high |
| `apps/brain/brain/interview/inbound.py` | 82 | simple (2/5) | medium |
| `apps/brain/brain/resolve/resolve.py` | 152 | moderate (3/5) | low |

**Action:** Replace the frontier LLM call with a POST to `/classify`.

## 2. Replace Extraction Calls with `sd_extract`

**Estimated savings: ~95% per call**

| File | Line | Complexity | Confidence |
|---|---|---|---|
| `apps/brain/brain/extract/relations.py` | 231 | highly_complex (5/5) | low |
| `apps/brain/brain/extract/flat.py` | 255 | simple (2/5) | medium |
| `apps/brain/brain/read/dates.py` | 189 | trivial (1/5) | high |

**Action:** Replace the frontier LLM call with a POST to `/extract`.

## ScaleDown HTTP API

All ScaleDown SLMs are called via REST. No SDK required.

**Base URL:** `https://api.scaledown.xyz`
**Auth:** `x-api-key: $SCALEDOWN_API_KEY`
**Docs:** https://docs.scaledown.ai/api-reference/

### sd_classify

```http
POST /classify
Content-Type: application/json
x-api-key: $SCALEDOWN_API_KEY

{
  "text": "<input text>",
  "labels": [
    { "name": "billing",   "rubric": "Does this describe a billing issue?" },
    { "name": "technical", "rubric": "Does this describe a technical issue?" }
  ]
}
```

Response: `{ "top_label": "billing", "scores": { "billing": 0.91, "technical": 0.09 }, "labels": [...], "ocr_text": null }`

### sd_extract

```http
POST /extract
Content-Type: application/json
x-api-key: $SCALEDOWN_API_KEY

{
  "text": "<input text>",
  "entities": {
    "Name":  "Full name of a person",
    "Email": "Email address"
  }
}
```

Response: `{ "entities": [{ "text": "Alice", "type": "Name", "confidence": 0.98, "start": 0, "end": 5 }], "structured_result": { "Name": "Alice", "Email": "..." }, "ocr_text": null }` — read clean per-field values from `structured_result`.

### sd_compress

```http
POST /compress/raw/
Content-Type: application/json
x-api-key: $SCALEDOWN_API_KEY

{
  "context": "<retrieved documents or long background text>",
  "prompt":  "<user query or instruction>",
  "scaledown": { "rate": "auto" }
}
```

Response: `{ "compressed_prompt": "...", "successful": true, "original_prompt_tokens": 4200, "compressed_prompt_tokens": 1400 }`

### sd_summarize *(private preview)*

```http
POST /summarization/abstractive
Content-Type: application/json
x-api-key: $SCALEDOWN_API_KEY

{
  "text": "<document to summarize>",
  "instructions": "Be concise."
}
```

Response: `{ "summary": "...", "input_chars": 4200, "output_chars": 380, "latency_ms": 120, "ocr_text": null }`

Response: `{ "summary": "..." }`

Get a free API key (50M tokens free) at: https://scaledown.ai/dashboard

---
*Generated by ScaleDown Migration Agent v1 at 2026-11-18T19:49:18.784Z*

