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
  GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  REASONING_EFFORT_SETTING_KEYS,
  ROUTE_SETTING_KEYS,
} from '@oracle/ai';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { ModelPicker, type ReasoningEffort } from './_components/model-picker';
import { STAGE_REQUIREMENTS, type Stage } from '@/lib/stage-requirements';

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
  /** null for general-purpose — has no stage requirements. */
  stage: Stage | null;
  effortSettingKey?: string;
  effortSettingDescription?: string;
  title: string;
  subtitle: string;
  description: React.ReactNode;
  settingDescription: string;
}

const MODEL_ROLES: RoleDef[] = [
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
  {
    settingKey: GENERAL_PURPOSE_ROUTE_SETTING_KEY,
    stage: null,
    title: 'General-purpose model',
    subtitle: 'Utility / fallback model for internal jobs',
    description: (
      <>
        Used for one-off internal tasks that don&apos;t fit the three stages
        above — taxonomy cluster naming, on-demand classification, ad-hoc
        admin queries. Pick whatever the current best general-purpose model
        is and update it here when a newer one ships. The picker draws from
        the full discovered catalog (no pool or stage requirements apply).
      </>
    ),
    settingDescription: 'General-purpose / utility model. Admin updates this when a newer model is available.',
  },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function isReasoningEffort(v: unknown): v is ReasoningEffort {
  return v === 'off' || v === 'low' || v === 'medium' || v === 'high';
}

export default async function AdminSettingsPage() {
  const db = getDirectDb();

  // Build the full list of settings keys we need to read — both model + effort.
  const allKeys: string[] = MODEL_ROLES.flatMap((r) =>
    r.effortSettingKey ? [r.settingKey, r.effortSettingKey] : [r.settingKey],
  );

  const rows = await db.select().from(settings).where(inArray(settings.key, allKeys));

  // Build lookup so we can pass the right current values to each picker.
  const currentValues: Record<string, unknown> = {};
  for (const row of rows) currentValues[row.key] = row.value;

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

      {MODEL_ROLES.map((role) => {
        const currentModel =
          typeof currentValues[role.settingKey] === 'string'
            ? (currentValues[role.settingKey] as string)
            : null;
        const rawEffort = role.effortSettingKey ? currentValues[role.effortSettingKey] : null;
        const currentEffort: ReasoningEffort | null = isReasoningEffort(rawEffort) ? rawEffort : null;

        return (
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
              />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
