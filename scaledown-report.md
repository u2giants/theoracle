# ScaleDown Migration Plan — oracle
> Generated: 2026-10-27T23:11:03.812Z
> Report version: 1

## Current AI Architecture

Two generations of code coexist. The legacy Oracle (TypeScript: `packages/ai` + `apps/workers/src/trigger`) runs a Trigger.dev pipeline: documents and Teams/chat messages are segmented into "shapes", candidate claims are extracted with a 400-line multi-task prompt (extract claim + classify claim kind + classify domain + flag sensitivity + propose entities), validated, synthesized into Brain sections, and served through a chat answer prompt; side workers adjudicate contradictions and draft chat interjections. Providers are routed through OracleAIClient adapters (OpenAI, Anthropic, Gemini, DeepSeek, Qwen). The replacement Oracle 2 (Python: `services/oracle-brain`) has three model call sites: a whole-document process extraction through graphrag-sdk on FalkorDB (preview-gated), a holistic answer plus a grounding-review call that both paste every source document into the prompt, and an unwired vision reader for PDF pages. The default Oracle 2 answer engine is deterministic keyword matching with no model at all. No test or CI step calls a real model.

| Usage Pattern | Provider | Files | Purpose |
|---|---|---|---|
| Source segmentation (shape classification) | openai-compatible via OracleAIClient | `packages/ai/src/prompts/workflow-read.ts` | Classify each passage as process / responsibilities / reference / ruleset / conversation / narrative |
| Claim extraction (multi-task) | openai-compatible via OracleAIClient | `packages/ai/src/prompts/extraction-system.ts`, `apps/workers/src/trigger/claim-extraction.ts` | Extract atomic claims with quotes; assign claim kind, domain, sensitivity, entities |
| Workflow / responsibility structured read | openai-compatible via OracleAIClient | `packages/ai/src/prompts/workflow-read.ts` | Extract ordered steps, handoffs, owners, rules as JSON with quote-repair passes |
| Brain synthesis | openai-compatible via OracleAIClient | `apps/workers/src/trigger/brain-synthesis.ts` | Rewrite approved claims into Brain sections (generation) |
| Contradiction adjudication + interjection | openai-compatible via OracleAIClient | `apps/workers/src/trigger/contradiction-watcher.ts`, `apps/workers/src/trigger/lull-interjection.ts` | Decide if two claims contradict (label), then draft a chat question |
| Employee chat answer | openai-compatible via OracleAIClient | `packages/ai/src/prompts/oracle-system.ts`, `packages/ai/src/retrieval.ts` | Retrieval-augmented COO-persona chat |
| Oracle 2 whole-document process extraction | openai (JSON mode) via graphrag-sdk | `services/oracle-brain/oracle_brain/graph/graphrag.py`, `.../holistic_runtime.py` | Extract process objects and links with exact quotes; load into FalkorDB |
| Oracle 2 holistic answer + grounding review | openai via graphrag-sdk | `services/oracle-brain/oracle_brain/graph/graphrag.py` | Paste every source's full text into one prompt, answer, then review |
| Oracle 2 visual page reader | openai vision | `services/oracle-brain/oracle_brain/ingest/originals.py` | Transcribe PDF page images to JSON; no production caller |

## Summary

| Metric | Value |
|---|---|
| Files scanned | 21889 |
| Files with AI API calls | 7 |
| Total integration opportunities | 9 |
| Providers detected | openai-compatible (OracleAIClient), openai (graphrag-sdk), openai vision |

### Call Complexity Breakdown

| Complexity | Count |
|---|---|
| simple | 1 |
| moderate | 3 |
| complex | 2 |
| highly_complex | 3 |

## 1. Replace Classification Calls with `sd_classify` (~95% per call)

| File | Line | Complexity | Confidence |
|---|---|---|---|
| `packages/ai/src/prompts/workflow-read.ts` | 22 | simple (2/5) | high |
| `packages/ai/src/prompts/extraction-system.ts` | 1 | complex (4/5) | high |
| `apps/workers/src/trigger/contradiction-watcher.ts` | 67 | moderate (3/5) | high |

Source segmentation is the highest-volume item: it runs on every passage of every document and transcript line. At hundreds of documents and tens of thousands of transcript lines this is where most of the saving lands.

## 2. Replace Extraction Calls with `sd_extract` (~90-95% per call)

| File | Line | Complexity | Confidence |
|---|---|---|---|
| `packages/ai/src/prompts/extraction-system.ts` | 1 | complex (4/5) | high |
| `packages/ai/src/prompts/workflow-read.ts` | 7 | moderate (3/5) | medium |
| `services/oracle-brain/oracle_brain/graph/graphrag.py` | 199 | complex (4/5) | medium |

Flat entity/field extraction (people, roles, systems, steps, artifacts, rules, quotes) can move to `sd_extract`. Relationship inference (which step hands off to which, what depends on what, what is an exception to what) must stay with a frontier model; that is the "big picture" step and SLMs do not do it.

## 3. Compress Context Before LLM Calls with `sd_compress` (50-70% of input tokens)

| File | Line | Complexity |
|---|---|---|
| `apps/workers/src/trigger/brain-synthesis.ts` | 376 | highly_complex (5/5) |
| `packages/ai/src/prompts/oracle-system.ts` | 7 | highly_complex (5/5) |
| `services/oracle-brain/oracle_brain/graph/graphrag.py` | 396 | highly_complex (5/5) |

Note on graphrag.py line 396: compression only delays the real problem. Pasting every source document into one prompt cannot work at hundreds of documents. Replace with real retrieval over a graph plus hierarchical summaries.

## 4. Complex Call Decompositions

### `packages/ai/src/prompts/extraction-system.ts` (line 1) — complex (4/5)
| Step | Purpose | Handler |
|---|---|---|
| 1 | Extract candidate statements with exact quote and entity mentions | ScaleDown `sd_extract` |
| 2 | Assign claimKind (six labels) | ScaleDown `sd_classify` |
| 3 | Assign knowledge domain | ScaleDown `sd_classify` |
| 4 | Flag HR/PII sensitivity (owner says data is not secret; optional) | ScaleDown `sd_classify` |

### `packages/ai/src/prompts/workflow-read.ts` (line 7) — moderate (3/5)
| Step | Purpose | Handler |
|---|---|---|
| 1 | Pull steps, actors, systems, artifacts, rules as flat records with quotes | ScaleDown `sd_extract` |
| 2 | Order steps and infer handoffs/dependencies | Frontier LLM |

### `apps/workers/src/trigger/contradiction-watcher.ts` (line 67) — moderate (3/5)
| Step | Purpose | Handler |
|---|---|---|
| 1 | contradicts / compatible / unclear | ScaleDown `sd_classify` |
| 2 | Draft the one-line question | Frontier LLM |

### `services/oracle-brain/oracle_brain/graph/graphrag.py` (line 199) — complex (4/5)
| Step | Purpose | Handler |
|---|---|---|
| 1 | Extract objects (role, step, system, artifact, rule, exception, decision, output) with quotes and scope | ScaleDown `sd_extract` |
| 2 | Classify ambiguous object kinds (eight labels) | ScaleDown `sd_classify` |
| 3 | Infer typed links between objects, preserving exceptions and contradictions | Frontier LLM |

### Not replaceable
- `services/oracle-brain/oracle_brain/ingest/originals.py` line 112: vision transcription of PDF pages and diagrams. No ScaleDown SLM handles images; keep a vision model.
- Cross-document synthesis, hierarchical (community) summaries, recommendation writing, interview questioning: frontier model only. `sd_summarize` can produce per-document and per-transcript-chunk summaries as cheap input to that step, but it is in private preview.

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

{"text":"<input text>","labels":[{"name":"billing","rubric":"Does this describe a billing issue?"},{"name":"technical","rubric":"Does this describe a technical issue?"}]}
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

Get a free API key (50M tokens free) at: https://scaledown.ai/dashboard

---
*Generated by ScaleDown Migration Agent v1 at 2026-10-27T23:11:03.812Z*
