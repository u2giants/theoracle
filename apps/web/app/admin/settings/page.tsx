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
- Description of structure and meaning: what the boxes/nodes are, how arrows/lines connect them, what each table row contains, and spatial grouping (columns, swimlanes, before/after, hierarchy, sequence).
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

// Clipboard "job brief" text by auxiliary-model id. Declared after the brief
// literals (which are large) so the earlier AUX_PRESENTATION map stays free of
// forward references. Aux models without a brief simply omit an entry.
const AUX_CLIPBOARD_BRIEFS: Record<string, string> = {
  vision: VISION_MODEL_BRIEF,
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
