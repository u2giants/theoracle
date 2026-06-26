// Admin → Settings tab.
// Reads all model + reasoning-effort settings from the DB server-side, passes
// to client pickers. Per-stage required-capability icons rendered from the
// shared @/lib/stage-requirements module so they match the model-pool page.

import React from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { inArray } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import {
  REASONING_EFFORT_SETTING_KEYS,
  ROUTE_SETTING_KEYS,
  AUXILIARY_MODELS,
  resolveModelRoute,
  type AuxiliaryCapabilityFilter,
} from '@oracle/ai';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { ModelPicker, type ReasoningEffort } from './_components/model-picker';
import { DispatchModeToggle, type DispatchMode } from './_components/dispatch-mode-toggle';
import { TeamsLiveBotCard } from './_components/teams-live-bot-card';
import { STAGE_REQUIREMENTS, type Stage } from '@/lib/stage-requirements';

const EXTRACTION_DISPATCH_MODE_KEY = 'extraction_dispatch_mode';

// ---------------------------------------------------------------------------
// Per-stage requirement icons — server component, no 'use client'.
// Pulls the same predicates the picker uses for filtering.
// ---------------------------------------------------------------------------

function StageRequirementIcons({ stage }: { stage: Stage }) {
  const reqs = STAGE_REQUIREMENTS[stage];
  return (
    <div className="flex flex-wrap items-center gap-2.5 mt-3">
      {reqs.map((r, i) => (
        <span
          key={i}
          title={r.label}
          className="flex items-center gap-1 text-xs font-medium text-muted-foreground"
        >
          <r.icon className={cn('size-3.5', r.color)} />
          {r.label}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The four configurable model roles (3 stages + general-purpose).
// ---------------------------------------------------------------------------

interface RoleDef {
  settingKey: string;
  /** null for auxiliary models — they have no pipeline-stage requirement icons. */
  stage: Stage | null;
  effortSettingKey?: string;
  effortSettingDescription?: string;
  title: string;
  subtitle: string;
  description: React.ReactNode;
  settingDescription: string;
  /** Optional detailed role brief copied to the clipboard from the picker. */
  clipboardBrief?: string;
  /** Set for auxiliary models — passed to the picker to drive list + filtering. */
  auxiliary?: { id: string; requiredCapability?: AuxiliaryCapabilityFilter };
}

/**
 * Web-side presentation for each auxiliary model, keyed by registry id. The
 * data-layer facts (setting keys, capability filter, default route) live in the
 * @oracle/ai AUXILIARY_MODELS registry; this only holds the rich copy that
 * can't live in the data layer (JSX descriptions, the clipboard brief).
 *
 * To add a new auxiliary model: add an entry to AUXILIARY_MODELS in @oracle/ai
 * and a matching presentation entry here — no other code changes needed.
 */
const AUX_PRESENTATION: Record<
  string,
  {
    subtitle: string;
    description: React.ReactNode;
    settingDescription: string;
    effortSettingDescription?: string;
  }
> = {
  vision: {
    subtitle: 'Reads uploaded images (diagrams, screenshots, photos)',
    description: (
      <>
        When an employee uploads an <strong>image</strong> (PNG, JPEG, WebP, or
        HEIC), this model transcribes it to faithful text — verbatim text plus
        the meaning of diagrams, tables, and layout — before claim extraction
        runs over that text. The picker is filtered to{' '}
        <strong>vision-capable</strong> models from any provider. The shipped
        default is the Gemini extraction model; change it here with no redeploy.
      </>
    ),
    settingDescription: 'Vision model used to transcribe uploaded images to text before extraction.',
    effortSettingDescription:
      'Reasoning effort for image transcription. Most vision models ignore this; leave Off unless the chosen model benefits.',
  },
  general: {
    subtitle: 'Utility / fallback model for internal jobs',
    description: (
      <>
        Used for one-off internal tasks that don&apos;t fit the three stages
        above — taxonomy cluster naming, on-demand classification, ad-hoc admin
        queries. Pick whatever the current best general-purpose model is and
        update it here when a newer one ships. The picker draws from the full
        discovered catalog (no pool or stage requirements apply).
      </>
    ),
    settingDescription: 'General-purpose / utility model. Admin updates this when a newer model is available.',
  },
  translation: {
    subtitle: 'Translates approved claims into employees’ languages',
    description: (
      <>
        When a claim is approved, this model translates its summary into the
        other supported language(s) so China-group employees read claims in
        Simplified Chinese while everyone else reads English (one unified
        knowledge graph). Evidence quotes and the synthesized Brain stay in their
        original language. The picker draws from the full discovered catalog — pick
        a strong <strong>Chinese-native</strong> model (e.g. Qwen) for best
        Mandarin quality. The shipped default is the multilingual Sonnet route.
      </>
    ),
    settingDescription: 'Model used to translate approved claim summaries for the bilingual claim layer.',
  },
};

const VISION_MODEL_BRIEF = `THE ORACLE — "Image Vision Model" role brief
(Paste this into a model-evaluation assistant or vendor comparison to judge whether a given model is the right pick for this setting.)

PURPOSE
This model performs Pass 1 of The Oracle's image-ingestion pipeline: it converts a single uploaded image into a faithful, self-contained PLAIN-TEXT rendering. It does NOT create knowledge itself — its text output is handed to a separate extraction model that mines structured "claims" from it. Its only job is high-fidelity image-to-text transcription and description. Everything downstream depends on this text being complete and accurate.

WHERE IT SITS IN THE PIPELINE
An employee uploads an image in a channel -> this model transcribes it to text -> the text is chunked, embedded, and stored as document_chunks -> a separate extraction model pulls operational claims, and each claim must quote this text exactly (deterministic quote-validation). If this model omits or hallucinates content, the knowledge base becomes silently wrong. Fidelity matters more than eloquence.

WHAT IT IS FED (input)
- Exactly ONE raw image per call, sent inline (PNG, JPEG, WebP, or HEIC).
- A fixed system instruction telling it to transcribe verbatim and describe visual meaning.
- A one-line request naming the file.
- No conversation history, no other documents, no tools.
Typical images: process diagrams, flowcharts, org charts, spreadsheets/tables, screenshots of apps or emails, photos of printed documents, whiteboards, shipping labels, handwritten notes, product photos.

WHAT IS EXPECTED (output)
- Plain text only — no markdown code fences, no "Here is..." preamble.
- VERBATIM transcription of every piece of visible text: labels, headings, every table cell, captions, callouts, stamps, axis labels, legends, handwriting.
- Diagrams/flowcharts/org charts rendered as an explicit TEXT TOPOLOGY — nodes as [Shape/Color: "verbatim label"], edges as annotated directional arrows ([A] --(condition)--> [B]), swimlanes/columns as headers — NOT free-form prose. Tables rendered row-by-row. Verbatim labels kept inside the nodes so they stay exactly quotable.
- Concrete operational content surfaced: rules, steps, routing, ownership, dates, quantities, statuses, conditions, exceptions.
- Honesty about uncertainty: explicitly flag anything unreadable or ambiguous; never invent detail.

PROCESS IT USES
A single, stateless, one-shot vision call. No caching (each image is unique), no tool calls, no multi-turn, no structured/JSON output. Just: see the image, emit faithful text.

WHAT MAKES A MODEL PERFECTLY SUITED
- Excellent OCR-grade text extraction, including dense tables and messy or handwritten text.
- Strong document and diagram understanding — reads charts, flowcharts, forms, and layouts, not just loose text.
- High instruction-following discipline: verbatim fidelity, no embellishment, no hallucination, and willingness to say "unreadable."
- Preserves reading order and table structure when rendering to prose.
- Generous max OUTPUT length, enough to fully render dense, text-heavy images.
- Low cost and reasonable latency: this runs once per uploaded image at volume and is asynchronous (no human waiting), so throughput and cost matter more than sub-second speed.
- High reliability and availability.
- Multilingual text recognition if the business handles non-English documents.

CAPABILITIES IT NEEDS (hard requirements)
- Image input (vision) — non-negotiable.
- Plain-text generation with strong instruction adherence.
- Sufficient max output tokens to transcribe a full page of dense content.

CAPABILITIES IT DOES NOT NEED (do not pay for these; some actively hurt)
- Tool / function calling — unused.
- Structured outputs / JSON schema / response_format — output is prose, not schema.
- Extended "thinking" / reasoning budget — transcription is perception, not deliberation; reasoning mostly adds latency and cost with no fidelity gain. Keep reasoning effort Off or Low.
- Large context window — input is one image plus a short prompt, nowhere near long-context territory.
- Streaming — output is consumed by a background worker, not rendered live.
- PDF input — PDFs are handled by a separate parsing path, not this model.
- Audio / video — out of scope.

BOTTOM LINE
Pick the cheapest, most reliable vision model with the best OCR plus document/diagram comprehension and the strictest instruction-following. Ignore reasoning, tools, structured output, and long context — they are irrelevant here, and reasoning effort should stay low.`;

const INTERVIEW_MODEL_BRIEF = `THE ORACLE — "Interview Model" role brief
(Paste this into a model-evaluation assistant or vendor comparison to judge whether a given model is the right pick for this setting.)

PURPOSE
This model is The Oracle's employee-facing conversation engine. It answers direct chat messages, asks clarifying questions, and helps employees surface operational knowledge without pretending the knowledge graph contains facts it does not contain. It is the human interface to the system, so tone, latency, groundedness, and restraint all matter.

WHERE IT SITS IN THE PIPELINE
An employee sends a chat message -> the app deterministically retrieves recent conversation, open gaps, approved claims, Brain snippets, and relevant evidence -> this model writes the assistant reply -> the reply and usage metadata are stored for audit. It does NOT perform live retrieval through model-side tools; retrieval happens before the model call and is injected into the prompt. It should use the supplied evidence, ask follow-up questions when knowledge is thin, and avoid making unsupported business assertions.

WHAT IT IS FED (input)
- The Oracle system prompt and conversation rules.
- Recent channel messages and the user's latest message.
- Deterministically retrieved approved claims, quotes, open gaps, Brain snippets, and metadata when relevant.
- Optional image/document attachment text or image parts when the selected route supports vision.
- Provider cache hints and, for Qwen, a reusable session handle.
Typical topics: process questions, shipment routing, product-development decisions, customer exceptions, designer file practices, system workflows, meeting follow-ups, and "is this still true?" recertification questions.

WHAT IS EXPECTED (output)
- A helpful, grounded chat response to the employee.
- Usually one concise answer or one high-value follow-up question.
- No invented policy, no fake citations, no claim IDs exposed to the employee unless the UI explicitly asks for them.
- Clear distinction between "the approved knowledge says..." and "I do not have enough evidence yet."
- Warm, tactful language for people-sensitive or blame-prone topics.
- Good behavior in multi-turn context: remember the current conversation, but do not treat recent chat as approved truth unless the prompt labels it that way.

PROCESS IT USES
A synchronous, user-facing text or multimodal generation call. The user is waiting. The model receives prebuilt context blocks and must compose a response directly. It may receive tool-oriented prompt structure, but the direct provider adapters do not run arbitrary Vercel AI SDK tools; choose a model for instruction following over agentic tool autonomy.

WHAT MAKES A MODEL PERFECTLY SUITED
- Low latency under real chat pressure, ideally comfortably under 8 seconds including retrieval and provider overhead.
- Excellent instruction following and refusal discipline: grounded answers, one-question behavior, no unsupported business facts.
- Strong long-context handling for channel history, retrieved evidence, and document/image attachment context.
- Good vision support for product photos, diagrams, screenshots, and uploaded-document images shared in chat.
- Tool/function-call capability and structured-output capability are useful because this role shares infrastructure with direct adapters and may be extended with more structured chat behaviors.
- Strong conversational tone: clear, calm, tactful, and natural with employees.
- Good cache behavior for reusable system and conversation prefixes.
- Reasonable cost: this runs on demand whenever employees chat, so cost can climb quickly.

CAPABILITIES IT NEEDS (hard requirements in the picker)
- Tool/function calling.
- Structured output or response-format support.
- Vision/image input.
- Context window greater than 100K tokens.

CAPABILITIES THAT ARE NICE TO HAVE
- Prompt caching, especially for stable system/context prefixes.
- Reasoning controls when they do not harm latency.
- PDF/file input if the provider route can use it directly, though much document ingestion happens elsewhere.

CAPABILITIES IT DOES NOT NEED MOST
- Very high reasoning budgets for every turn — often too slow and expensive for routine employee chat.
- Huge output length — replies should be concise.
- Image generation, audio, video, or batch processing.

BOTTOM LINE
Pick the fastest reliable model that can follow strict grounding rules, handle vision and long context, speak naturally to employees, and keep cost sane at chat volume. Do not pick a brilliant but slow model as the default unless evals prove the cheaper real-time model is materially insufficient.`;

const EXTRACTION_MODEL_BRIEF = `THE ORACLE — "Extraction Model" role brief
(Paste this into a model-evaluation assistant or vendor comparison to judge whether a given model is the right pick for this setting. Read the "#1 CRITERION" and the "MEASURED BENCHMARK" sections before forming an opinion — they overturn the intuition that the cheapest schema-valid model wins.)

PURPOSE
This model turns raw operational text into structured claim candidates. It is the first intelligence pass after messages, Teams transcripts, documents, and image transcriptions enter the system. It does not directly approve knowledge; deterministic validators and admin review decide what can become an approved claim. Whatever this model fails to extract is lost forever — nothing downstream re-reads the source to recover a relationship this model skipped. The knowledge graph can only ever be as complete as this pass.

WHERE IT SITS IN THE PIPELINE
Messages and document chunks are grouped into extraction batches -> this model receives the source text plus extraction instructions -> it returns structured JSON candidates with exact supporting quotes -> deterministic validation checks quote presence, schema validity, domains, entities, confidence, impact, and promotion rules -> approved or reviewable claims move into the knowledge graph. If the model omits the exact quote or invents text, that one candidate fails; if the model simply never emits a claim for a relationship that is plainly in the source, there is no error at all — the knowledge is just silently missing.

#1 CRITERION — RECALL / COMPLETENESS (this is the criterion that actually separates good extractors from bad ones)
The single most important property of an extraction model for The Oracle is how COMPLETELY it mines a dense source. Schema-validity, low cost, and low latency are table stakes — they do NOT distinguish a good model from a useless one, because the WORST models pass all three while extracting almost nothing. In a controlled production bake-off (2026-06, a 14-lane swimlane process diagram transcribed to ~65-75 directional edges), every candidate returned perfectly valid, schema-conforming JSON, yet recall varied by roughly 10x:
  - google/gemini-2.5-flash    -> 54 claims  (dependencies + process rules + exception/conditional rules)  ~15.5k output tokens  ~60s
  - vertex gemini-2.5-flash    -> 52 claims  ~16k output tokens  ~68s
  - openai/gpt-4.1-mini        -> 12 claims  ~3.7k output tokens  ~45s
  - openai/gpt-4o-mini         ->  9 claims  ~1.4k output tokens  ~14s
  - google/gemini-3.1-flash-lite ->  5 claims  ~1.4k output tokens  ~5s
The cheap, fast "mini"/"lite" models were fast and cheap PRECISELY BECAUSE they emitted little — they silently dropped 80-90% of the operational content and reported success. A model that finishes a dense diagram in a few seconds with ~1-2k output tokens is showing you a RED FLAG (severe under-extraction), not efficiency. Do not reward it for speed or price.

A GREAT EXTRACTOR ALSO CAPTURES STRUCTURE, NOT JUST COUNT
Beyond raw count, the best model captured claim-type VARIETY: it represented conditional/branch logic ("If Audit: Fail", "For existing products", dashed exception arrows) as exception_rule / conditional dependency claims, instead of flattening everything into generic "A then B" links. A model that returns many claims but all of one flat type has still lost the decision logic. Prefer models that preserve conditions, exceptions, and rules.

WHAT IT IS FED (input)
- One or more employee messages, transcript turns, or document chunks.
- Source metadata such as speaker, channel, document context, upload hints, and known domains/entities.
- A strict extraction schema and instructions for claim typing, evidence quotes, confidence, impact, domains, gaps, and entity proposals.
- For images, this role receives the text produced by the separate image-vision pass (often a dense, edge-per-line transcription of a flowchart/diagram), not the raw image itself.
Typical material: meeting transcripts, process explanations, exception rules, customer-specific routing, operational decisions, file-handling rules, system workflows, swimlane process diagrams, and policy/practice discrepancies. Diagram transcriptions are the densest and most demanding input — they are where weak models collapse.

WHAT IS EXPECTED (output)
- Strict structured JSON matching the extraction schema.
- A claim for EVERY operationally meaningful relationship, rule, dependency, exception, and handoff the source actually supports — exhaustive coverage, not a representative sample.
- Exact quote strings copied verbatim from the input text, not paraphrases.
- Accurate claim type (and faithful use of conditional/exception types where the source has branch logic), summary, confidence score, impact score, knowledge domains, entities, and suggested follow-up gaps.
- Conservative handling of genuine ambiguity (lower confidence / gaps) — but NOT an excuse to skip content that is plainly stated.
- No polished prose; this is machine-consumed extraction output.

PROCESS IT USES
An asynchronous structured-output call (sync API or provider Batch API per extraction dispatch mode). Nobody is waiting in the UI, so LATENCY IS CHEAP HERE: a model that takes ~60s and extracts 54 claims is far better than one that takes 5s and extracts 5. Do not treat slower as worse for this role. The system tolerates minute-scale calls; the adapter timeout is 180s. The model result always passes through deterministic validators before promotion, so the failure mode to fear is not "too slow" — it is "schema-broken" or, far more insidiously, "schema-valid but shallow."

WHAT MAKES A MODEL PERFECTLY SUITED (in priority order)
1. HIGH RECALL on dense sources — extracts most/all of the relationships in a packed diagram or long transcript (see MEASURED BENCHMARK). This dominates every other factor.
2. STRUCTURE FIDELITY — preserves conditions, exceptions, and rule types rather than flattening to generic links.
3. NATIVE STRICT JSON-schema structured output (not a loose tool-call shim — see KNOWN PITFALLS).
4. Exact quote fidelity — copies verbatim spans from noisy transcripts and document text.
5. Large enough max-output-token budget to emit dozens of claims without truncating.
6. Good domain/entity reasoning across messy business language.
7. THEN, as a tiebreaker among models with comparable recall and fidelity: lower cost and Batch API support for high-volume runs. Cost is a tiebreaker, never a primary filter — choosing a cheaper model that under-extracts is a false economy that permanently shrinks the knowledge graph.

MEASURED BENCHMARK — how to read a candidate's numbers
On a single dense diagram (~65-75 edges): 50+ claims with mixed types = excellent; 30-50 = acceptable; under ~20 = under-extracting; under ~12 = disqualifying for this role no matter how cheap or fast or schema-clean it is. Output-token volume is a proxy: a dense diagram should pull well over ~8-10k output tokens from a strong extractor; ~1-2k output tokens on dense input means the model gave up early.

HOW TO EVALUATE A CANDIDATE (do this, don't reason in the abstract)
Feed the candidate a real dense diagram transcription (edge-per-line swimlane flowchart) under the production extraction schema, then check, in order: (a) did it return valid schema JSON; (b) HOW MANY claims vs. the number of edges/relationships in the source (recall is the headline); (c) claim-type variety — did it capture conditional/exception logic or flatten everything; (d) are the exact quotes verbatim substrings of the source; (e) only then, cost and latency. Test against the CURRENT adapters: earlier "returned 0 claims" results for some models were caused by now-fixed adapter bugs (OpenAI strict-schema required-fields, a Gemini 60s timeout, a Gemini thinking-config incompatibility), not by the models themselves — re-test rather than trusting stale failures.

CAPABILITIES IT NEEDS (hard requirements in the picker)
- Structured output / response-format support — PREFERABLY NATIVE strict JSON-schema (see KNOWN PITFALLS: a looser tool-call mode is a real risk here, not an equivalent).
- Context window greater than 100K tokens.
- Enough max-output-token budget to emit EVERY claim for a dense batch. If the JSON truncates mid-array it parses as a bare string and the ENTIRE batch is discarded — a dense diagram can produce 50+ claims, so do not pick a model with a small output cap, and verify the model actually USES that budget (under-extractors stop early even when the cap is generous).
- Demonstrated high recall on a dense test input (per HOW TO EVALUATE) — treat this as a hard gate, not a nicety.

CAPABILITIES THAT ARE NICE TO HAVE
- Prompt caching for stable extraction prompts and schemas.
- Reasoning controls at low/medium effort for nuanced domain and impact scoring (the current winner runs with reasoning effort OFF and still extracts richly, so reasoning is not required for recall).
- Batch API support in the adapter/provider for cheaper high-volume runs.

CAPABILITIES IT DOES NOT NEED
- Chatty conversational style.
- Streaming — workers consume the final JSON only.
- Raw speed / lowest latency — explicitly NOT a priority; this is background work and shallow-but-fast is the trap.
- Native PDF input for this stage specifically; documents are usually parsed/chunked before extraction.
- Vision/image input for this stage specifically; images are transcribed by the separate Image Vision model before extraction receives text.

KNOWN PITFALLS
1. UNDER-EXTRACTION HIDING BEHIND VALID JSON (the most common and most damaging mistake). The "mini"/"lite"/cheapest tier of most families returns clean, schema-valid JSON and looks great in a quick smoke test, but extracts a small fraction of a dense source. Because there is no error, the gap is invisible until someone notices the graph is missing most of a process. Never pick an extraction model on schema-validity + price alone; always measure recall on dense input first.
2. STRICT JSON vs. LOOSE "TOOL-CALL" structured output. Providers WITHOUT a native strict JSON-schema mode (e.g. Qwen and DeepSeek via the OpenAI-compatible API) fall back to a looser TOOL-CALL mechanism that does not strictly enforce the schema. In production, qwen3.7-plus repeatedly MALFORMED FIELDS — scores as strings/null, domains outside the enum, evidence as a non-object — and because one malformed claim fails the whole extraction window, the run produced ZERO claims even though the upstream image transcription was perfect. The Gemini family (Google / Vertex) and OpenAI use native JSON-schema and conform far more reliably. Strongly prefer a native-strict-JSON model here.

BOTTOM LINE
Optimize for RECALL on dense operational sources, then structure fidelity, then native-strict-JSON reliability and exact quotes — and only then cost. The proven production pick is google/gemini-2.5-flash (rich, varied, faithful, native strict JSON, ~60s/batch with reasoning off), with the Vertex gemini-2.5-flash route and a strict-JSON OpenAI model as fallbacks. The classic failure is choosing a cheaper/faster "mini" or "lite" model because it returns valid JSON in a smoke test; in this role that is a model that silently throws away most of your knowledge. A model that extracts everything in 60 seconds beats one that extracts a tenth of it in 5 — every time.`;

const SYNTHESIS_MODEL_BRIEF = `THE ORACLE — "Synthesis Model" role brief
(Paste this into a model-evaluation assistant or vendor comparison to judge whether a given model is the right pick for this setting.)

PURPOSE
This model maintains The Oracle's Brain sections: versioned, evidence-backed Markdown documents that summarize approved business knowledge. It consolidates many approved claims into coherent operational guidance while preserving traceability back to claim IDs and evidence.

WHERE IT SITS IN THE PIPELINE
An admin or schedule selects a Brain section -> the worker loads the section, approved claims, existing content, and related metadata -> this model proposes a structured synthesis diff and updated Markdown -> deterministic validators check unsupported names, claim references, structured shape, and traceability -> valid versions can become the current Brain section. Failed versions are stored for review but not published.

WHAT IT IS FED (input)
- Up to hundreds of approved claims for a section, with summaries, evidence, domains, entities, timestamps, and claim IDs.
- Existing Brain section content and version history.
- Instructions to map every substantive paragraph back to approved claim IDs.
- Contradiction/staleness context when available.
Typical sections: departmental process knowledge, customer-specific exceptions, routing rules, product-development workflows, file-handling practices, and operational system procedures.

WHAT IS EXPECTED (output)
- Structured JSON containing synthesis changes plus updated Markdown.
- Clear, readable Brain-section prose that compresses many claims into useful operational knowledge.
- Every substantive paragraph tied to approved claim IDs.
- Explicit handling of contradictions, exceptions, and stale/uncertain knowledge.
- No invented names, policies, customers, dates, or procedures.
- Respect for existing section structure when updating rather than rewriting needlessly.

PROCESS IT USES
An asynchronous, high-judgment structured-output call. No employee is waiting, and quality matters far more than latency. The model must reason over a large evidence set, decide what belongs in the Brain section, preserve provenance, and emit output that deterministic validators can accept.

WHAT MAKES A MODEL PERFECTLY SUITED
- Very strong long-context comprehension, ideally far beyond 400K tokens.
- Excellent synthesis and contradiction reasoning across many short evidence items.
- Strong structured-output reliability.
- Strong output discipline: every paragraph grounded in claim IDs, no unsupported proper nouns.
- Large enough max output cap to produce complete Markdown sections and metadata.
- Reasoning controls are valuable here; higher effort can be worth it because runs are less frequent and quality-sensitive.
- Prompt caching can reduce cost for stable synthesis prompts and schemas.
- Cost matters, but this stage runs far less often than chat or extraction.

CAPABILITIES IT NEEDS (hard requirements in the picker)
- Context window greater than 400K tokens.
- Structured output or response-format support.
- Reasoning/thinking support.
- Output-length cap support.

CAPABILITIES THAT ARE NICE TO HAVE
- Prompt caching for stable prompts/schemas.
- Strong JSON schema support rather than loose JSON prompting.
- High max output tokens.
- Excellent instruction hierarchy and citation/provenance discipline.

CAPABILITIES IT DOES NOT NEED MOST
- Vision/image input — image content should already have become approved text claims before synthesis.
- Fast latency — it is a background/admin workflow.
- Streaming.
- Tool calling unless needed for structured-output mode.
- Batch processing, unless many sections are being regenerated at once.

BOTTOM LINE
Pick the highest-quality long-context reasoning model that reliably emits structured JSON and can produce grounded Markdown with claim-level provenance. This is the place to spend more for careful reasoning, because a bad synthesis can make the official Brain misleading even when the underlying claims are correct.`;

const TRANSLATION_MODEL_BRIEF = `THE ORACLE — "Translation Model" role brief
(Paste this into a model-evaluation assistant or vendor comparison to judge whether a given model is the right pick for this setting.)

PURPOSE
This model translates an approved business "claim" — a single short, factual operational statement — from its source language into another language, so employees can read the company's knowledge in their own language. The Oracle keeps ONE unified knowledge graph: a claim is authored once (its canonical text + supporting evidence stay in the original language) and this model produces a faithful rendering in the other language for display only. It does NOT create, interpret, summarize, or expand knowledge — it only re-expresses an existing claim in another language with zero drift.

WHERE IT SITS IN THE PIPELINE
A claim is extracted and approved -> an admin selects specific claims to direct to a language group (today: the China team, Simplified Chinese) -> the claim-translation background worker calls this model once per claim per target language -> the translated text is embedded (same embedding model as the canonical claim) and stored in claim_translations -> at chat time, retrieval shows each reader the rendering in their locale (COALESCE: translation if present, else the canonical text). The evidence quote and the synthesized "Brain" are NEVER translated — only the claim summary. So this model sits strictly on the read-side display path; nothing downstream re-derives meaning from its output except a human reading it and a semantic embedding for retrieval.

WHAT IT IS FED (input)
- Exactly ONE claim summary per call — typically one to three sentences of concise operational business prose (a rule, a routing decision, an ownership fact, a deadline, a status, an exception).
- A fixed system instruction telling it to translate faithfully into a named target language and output only the translation.
- The target language name.
- No conversation history, no other claims, no documents, no images, no tools.
Typical content: product-development steps, licensing/approval rules, shipment routing, customer-ops exceptions, designer file practices, ERP/PLM workflows. Expect proper nouns (people, products, systems, customers), internal codes, numbers, dates, and units.

WHAT IS EXPECTED (output)
- ONLY the translated text — no preamble, no quotes, no notes, no transliteration of the source.
- Exact preservation of meaning. No additions, omissions, softening, hedging, or editorializing — a mistranslated operational rule silently misleads the people who act on it.
- Natural, idiomatic register in the TARGET language — read like a native operations writer wrote it, not a literal word-for-word gloss. This matters most: employees read these to do their jobs.
- Faithful handling of proper nouns, product/system names, and codes — kept as-is unless a well-established target-language form exists; never invented.
- Numbers, dates, units, and quantities preserved exactly.
- Honest, conservative behavior on ambiguity — do not "improve" or guess; translate what is there.

PROCESS IT USES
A single, stateless, one-shot text-generation call per claim per language. Fully asynchronous — a background worker runs it; no human is waiting. Volume is LOW and bounded (only the specific claims an admin directs to a language group, not the whole corpus), and it is idempotent (re-run only when the source claim changes). There is no caching benefit (each claim is unique), no multi-turn, no tool use, and no structured/JSON output — the output is plain prose.

WHAT MAKES A MODEL PERFECTLY SUITED
- Best-in-class translation QUALITY for the specific language pair in use (here: English <-> Simplified Chinese), with idiomatic, natural target-language phrasing — not stilted literalism.
- For Chinese specifically, a Chinese-native model family (e.g. Qwen) typically has the strongest Mandarin register and handling of business idiom; weigh that heavily.
- High instruction-following discipline: outputs ONLY the translation, preserves proper nouns/numbers, never adds commentary.
- Faithfulness over fluency-at-any-cost: never drops or invents operational detail.
- Good terminology consistency on domain jargon and named entities.
- Because the job is async, low-volume, and not user-facing, COST and LATENCY barely matter — do not trade translation fidelity to save either. Prefer the higher-quality tier (e.g. a "max"/flagship tier) over a "flash"/cheap tier.
- High reliability/availability is nice but not critical (the worker is idempotent and retryable).

CAPABILITIES IT NEEDS (hard requirements)
- Excellent bilingual generation for the exact language pair in use.
- Strong instruction adherence for "translate only, output nothing else."
- Enough max output to cover a few sentences (tiny — never an issue).
- Modest context window — input is one short claim plus a short prompt; long-context is irrelevant.

CAPABILITIES IT DOES NOT NEED (do not pay for these; some actively hurt)
- Vision / image input — text only.
- Tool / function calling — unused.
- Structured outputs / JSON schema / response_format — output is plain prose.
- Extended "thinking" / reasoning budget — translation of a short statement is not deliberation; reasoning mostly adds latency and cost and can encourage over-editing. Keep reasoning effort Off or Low.
- Long context window — one short claim per call.
- Streaming — consumed by a background worker, not rendered live.
- Batch API discount — volume is low and selective; not worth the added plumbing.
- PDF / audio / video — out of scope.

BOTTOM LINE
Pick the model with the best, most natural translation quality for your exact language pair and the strictest "output only the translation" discipline — a Chinese-native flagship (e.g. Qwen-Max-tier) is a strong default for English<->Chinese. Ignore reasoning, tools, structured output, vision, and long context; keep reasoning effort low. Since it runs async on only the claims you direct to a language group, spend for fidelity, not speed or cost. Validate the final choice with a small A/B (this model vs one alternative) on ~15 real claims judged by a bilingual reviewer.`;

// Clipboard "job brief" text by auxiliary-model id. Declared after the brief
// literals (which are large) so the earlier AUX_PRESENTATION map stays free of
// forward references. Aux models without a brief simply omit an entry.
const AUX_CLIPBOARD_BRIEFS: Record<string, string> = {
  vision: VISION_MODEL_BRIEF,
  translation: TRANSLATION_MODEL_BRIEF,
};

const STAGE_MODEL_ROLES: RoleDef[] = [
  {
    settingKey: ROUTE_SETTING_KEYS.interview,
    stage: 'interview',
    effortSettingKey: REASONING_EFFORT_SETTING_KEYS.interview,
    effortSettingDescription: 'Reasoning effort for the Interview stage. Translated per provider at inference time.',
    title: 'Interview model',
    subtitle: 'Real-time Oracle chat',
    description: (
      <>
        Called synchronously every time an employee sends a message. The employee
        is watching a &ldquo;thinking…&rdquo; indicator. This model must support{' '}
        <strong>tool use</strong> and follow strict one-question-per-reply output
        rules. Employees regularly share images (product photos, diagrams) and
        upload documents — <strong>vision</strong> and a long enough{' '}
        <strong>context window</strong> are both required. Latency is user-facing —
        aim for under 8 s including tool calls.
      </>
    ),
    settingDescription: 'Direct-provider model for real-time Oracle interview chat.',
    clipboardBrief: INTERVIEW_MODEL_BRIEF,
  },
  {
    settingKey: ROUTE_SETTING_KEYS.extraction,
    stage: 'extraction',
    effortSettingKey: REASONING_EFFORT_SETTING_KEYS.extraction,
    effortSettingDescription: 'Reasoning effort for async claim extraction. Higher = better recall at higher cost.',
    title: 'Extraction model',
    subtitle: 'Async claim extraction from messages & documents',
    description: (
      <>
        Runs in the background every 4 hours (and on document upload) via
        Trigger.dev. Reads batches of employee messages or document chunks and
        outputs structured JSON: claim type, summary, impact score, confidence
        score, exact supporting quote, knowledge domains, and suggested gaps.
        Nobody is waiting — optimise for <strong>accuracy</strong> and{' '}
        <strong>structured output reliability</strong>. Reasoning models with
        non-zero effort generally improve quality of impact / confidence scoring.
      </>
    ),
    settingDescription: 'Direct-provider model for async claim extraction from messages and documents.',
    clipboardBrief: EXTRACTION_MODEL_BRIEF,
  },
  {
    settingKey: ROUTE_SETTING_KEYS.synthesis,
    stage: 'synthesis',
    effortSettingKey: REASONING_EFFORT_SETTING_KEYS.synthesis,
    effortSettingDescription: 'Reasoning effort for brain synthesis. High effort recommended for contradiction reasoning.',
    title: 'Synthesis model',
    subtitle: 'Periodic Brain section synthesis',
    description: (
      <>
        Runs on a weekly schedule and on admin trigger. Reads up to 200 approved
        claims per brain section and synthesizes a new versioned Markdown
        document where <em>every paragraph maps to approved claim IDs</em>. The
        output is validated by a backend rule engine — any hallucinated or
        untracked claim ID causes the run to fail. This model must handle{' '}
        <strong>very long context</strong>, produce{' '}
        <strong>structured JSON</strong>, and reason carefully about
        contradicting evidence. No latency requirement.
      </>
    ),
    settingDescription: 'Direct-provider model for brain section synthesis — long-context, structured output.',
    clipboardBrief: SYNTHESIS_MODEL_BRIEF,
  },
];

// Auxiliary-model cards are generated from the @oracle/ai registry so adding a
// new one is a one-line registry change plus an AUX_PRESENTATION entry.
const AUX_MODEL_ROLES: RoleDef[] = AUXILIARY_MODELS.map((def) => {
  const p = AUX_PRESENTATION[def.id];
  if (!p) {
    throw new Error(`Missing AUX_PRESENTATION entry for auxiliary model "${def.id}"`);
  }
  return {
    settingKey: def.routeSettingKey,
    stage: null,
    effortSettingKey: def.reasoningEffortSettingKey,
    effortSettingDescription: p.effortSettingDescription,
    title: def.label,
    subtitle: p.subtitle,
    description: p.description,
    settingDescription: p.settingDescription,
    clipboardBrief: AUX_CLIPBOARD_BRIEFS[def.id],
    auxiliary: { id: def.id, requiredCapability: def.requiredCapability },
  };
});

const MODEL_ROLES: RoleDef[] = [...STAGE_MODEL_ROLES, ...AUX_MODEL_ROLES];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function isReasoningEffort(v: unknown): v is ReasoningEffort {
  return v === 'off' || v === 'low' || v === 'medium' || v === 'high';
}

function providerModelId(provider: string, modelId: string): string {
  const prefix =
    provider === 'vertex'
      ? 'google'
      : provider === 'anthropic' ||
          provider === 'openai' ||
          provider === 'deepseek' ||
          provider === 'qwen'
        ? provider
        : provider;
  return `${prefix}/${modelId}`;
}

export default async function AdminSettingsPage() {
  const db = getDirectDb();

  // Build the full list of settings keys we need to read — both model + effort + dispatch mode.
  const allKeys: string[] = [
    ...MODEL_ROLES.flatMap((r) =>
      r.effortSettingKey ? [r.settingKey, r.effortSettingKey] : [r.settingKey],
    ),
    EXTRACTION_DISPATCH_MODE_KEY,
  ];

  const rows = await db.select().from(settings).where(inArray(settings.key, allKeys));

  // Build lookup so we can pass the right current values to each picker.
  const currentValues: Record<string, unknown> = {};
  for (const row of rows) currentValues[row.key] = row.value;

  const rawDispatchMode = currentValues[EXTRACTION_DISPATCH_MODE_KEY];
  const dispatchMode: DispatchMode = rawDispatchMode === 'batch' ? 'batch' : 'sync';

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Model configuration for all Oracle tasks. Each role has different
          capability and performance requirements — see descriptions below.
          Changes take effect on the next run of that task.
        </p>
        <p className="text-sm text-muted-foreground">
          The pickers below show models from your{' '}
          <Link
            href="/admin/settings/model-pool"
            className="underline underline-offset-2 text-foreground hover:text-foreground/70"
          >
            model pool
          </Link>
          . Stage requirements (capability flags + context-window thresholds)
          are enforced both here and on the pool page — they share the same
          source of truth.
        </p>
      </header>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Live Teams meeting bot</CardTitle>
          <CardDescription className="font-medium text-foreground/70">
            Bring Oracle into a meeting
          </CardDescription>
          <p className="text-sm text-muted-foreground mt-1">
            Oracle does not appear in the Microsoft Teams people picker yet.
            Paste a Teams meeting link here and Recall.ai will bring Oracle
            into the call as a bot participant.
          </p>
        </CardHeader>
        <CardContent>
          <TeamsLiveBotCard />
        </CardContent>
      </Card>

      {MODEL_ROLES.map((role) => {
        const currentModel =
          typeof currentValues[role.settingKey] === 'string'
            ? (currentValues[role.settingKey] as string)
            : null;
        const resolved =
          currentModel && role.stage ? resolveModelRoute(currentModel, role.stage) : null;
        const currentResolvedModel = resolved
          ? providerModelId(resolved.provider, resolved.modelId)
          : null;
        const rawEffort = role.effortSettingKey ? currentValues[role.effortSettingKey] : null;
        const currentEffort: ReasoningEffort | null = isReasoningEffort(rawEffort) ? rawEffort : null;

        const card = (
          <Card key={role.settingKey} className="max-w-2xl">
            <CardHeader>
              <CardTitle className="text-base">{role.title}</CardTitle>
              <CardDescription className="font-medium text-foreground/70">
                {role.subtitle}
              </CardDescription>
              <p className="text-sm text-muted-foreground mt-1">
                {role.description}
              </p>
              {role.stage && <StageRequirementIcons stage={role.stage} />}
            </CardHeader>
            <CardContent>
              <ModelPicker
                currentModel={currentModel}
                currentResolvedModel={currentResolvedModel}
                currentEffort={currentEffort}
                settingKey={role.settingKey}
                settingDescription={role.settingDescription}
                effortSettingKey={role.effortSettingKey}
                effortSettingDescription={role.effortSettingDescription}
                clipboardBrief={role.clipboardBrief}
                auxiliary={role.auxiliary}
              />
            </CardContent>
          </Card>
        );

        // After the Extraction card, inject the dispatch-mode toggle card —
        // it controls how the extraction worker dispatches (sync vs Batch API).
        if (role.stage === 'extraction') {
          return (
            <div key={role.settingKey} className="space-y-8">
              {card}
              <Card className="max-w-2xl">
                <CardHeader>
                  <CardTitle className="text-base">Extraction dispatch mode</CardTitle>
                  <CardDescription className="font-medium text-foreground/70">
                    Sync API vs provider Batch API
                  </CardDescription>
                  <p className="text-sm text-muted-foreground mt-1">
                    The Batch API runs claim extraction asynchronously at about 50% off
                    the sync price with a 24-hour SLA. Within a chat session the Oracle
                    still reads live message history, so conversation quality is
                    unchanged — only cross-session knowledge freshness drops by up to
                    24 hours. See <strong>DECISIONS.md D14</strong> for the full
                    trade-off analysis.
                  </p>
                </CardHeader>
                <CardContent>
                  <DispatchModeToggle currentMode={dispatchMode} />
                </CardContent>
              </Card>
            </div>
          );
        }

        return card;
      })}
    </div>
  );
}
