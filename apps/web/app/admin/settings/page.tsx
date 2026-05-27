// Admin → Settings tab.
// Reads all model settings from the DB server-side, passes to client pickers.
//
// P1 #1 fix: setting keys now use the correct _route suffix that workers read
// (ROUTE_SETTING_KEYS from @oracle/ai/routes). The legacy _model keys are no
// longer written here — any existing rows with the old keys continue to exist
// in the DB but are ignored by the production model paths.

import React from 'react';
import Link from 'next/link';
import { inArray } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { ROUTE_SETTING_KEYS, GENERAL_PURPOSE_ROUTE_SETTING_KEY } from '@oracle/ai';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { ModelPicker } from './_components/model-picker';
import { RequiredCapIcons, type CapKey } from './_components/caps';

// ---------------------------------------------------------------------------
// The three configurable model roles.
// ---------------------------------------------------------------------------

const MODEL_ROLES: {
  settingKey: string;
  title: string;
  subtitle: string;
  description: React.ReactNode;
  settingDescription: string;
  requirements: readonly string[];
  requiredCaps: CapKey[];
}[] = [
  {
    settingKey: ROUTE_SETTING_KEYS.interview,
    title: 'Interview model',
    subtitle: 'Real-time Oracle chat',
    description: (
      <>
        Called synchronously every time an employee sends a message. The employee
        is watching a &ldquo;thinking…&rdquo; indicator. This model must support{' '}
        <strong>tool use</strong> and follow strict one-question-per-reply output
        rules. Employees regularly share images (product photos, diagrams) and
        upload documents (routing guides, org charts, product specs, PDFs) —{' '}
        <strong>vision</strong> and <strong>file input</strong> are both required
        to read this material in-conversation. Latency is user-facing — aim for
        under 8 s including tool calls.
      </>
    ),
    settingDescription: 'Direct-provider model for real-time Oracle interview chat (Anthropic Claude Haiku 4.5 by default).',
    requirements: [
      'Tool use required',
      'Vision required (images, diagrams)',
      'File input required (PDFs, org charts, routing guides)',
      'Low latency (≤8 s)',
      'Strong instruction following',
      'Context: up to ~32K tokens (large documents)',
    ],
    requiredCaps: ['tools', 'vision', 'files'],
  },
  {
    settingKey: ROUTE_SETTING_KEYS.extraction,
    title: 'Extraction model',
    subtitle: 'Async claim extraction from messages & documents',
    description: (
      <>
        Runs in the background every 4 hours (and on document upload) via
        Trigger.dev. Reads batches of employee messages or document chunks and
        outputs structured JSON: claim type, summary, impact score, confidence
        score, exact supporting quote, knowledge domains, and suggested gaps.
        Nobody is waiting — optimise for <strong>accuracy</strong> and{' '}
        <strong>structured output reliability</strong>. Vision is needed for
        documents containing embedded images (flow charts, product specs).
      </>
    ),
    settingDescription: 'Direct-provider model for async claim extraction from messages and documents (Vertex Gemini Flash by default).',
    requirements: [
      'Structured / JSON output required',
      'Vision recommended (document images)',
      'File input recommended (PDFs, DOCX)',
      'High extraction accuracy',
      'No latency requirement (async)',
      'Context: variable, up to ~32K per batch',
    ],
    requiredCaps: ['tools', 'vision', 'files'],
  },
  {
    settingKey: ROUTE_SETTING_KEYS.synthesis,
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
    settingDescription: 'Direct-provider model for brain section synthesis — long-context, structured output (Vertex Gemini Flash by default).',
    requirements: [
      'Structured / JSON output required',
      'Long context (≥100K strongly recommended)',
      'No latency requirement (async, up to 10 min)',
      'High reasoning quality',
      'Context: potentially 100K+ tokens at scale',
    ],
    requiredCaps: ['tools', 'reasoning'],
  },
  {
    settingKey: GENERAL_PURPOSE_ROUTE_SETTING_KEY,
    title: 'General-purpose model',
    subtitle: 'Utility / fallback model for internal jobs',
    description: (
      <>
        Used for one-off internal tasks that don&apos;t fit the three stages
        above — taxonomy cluster naming, on-demand classification, ad-hoc
        admin queries. Pick whatever the current best general-purpose model
        is and update it here when a newer one ships. The picker draws from
        the full discovered catalog (no pool filter applies).
      </>
    ),
    settingDescription: 'General-purpose / utility model. Admin updates this when a newer model is available.',
    requirements: [
      'Tool use recommended',
      'Vision recommended',
      'Cheap to medium cost',
    ],
    requiredCaps: ['tools'],
  },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function AdminSettingsPage() {
  const db = getDirectDb();

  const rows = await db
    .select()
    .from(settings)
    .where(
      inArray(
        settings.key,
        MODEL_ROLES.map((r) => r.settingKey),
      ),
    );

  // Build a lookup so we can pass the right current value to each picker.
  const currentValues: Record<string, string | null> = {};
  for (const row of rows) {
    currentValues[row.key] =
      typeof row.value === 'string' ? row.value : null;
  }

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
          . Add or remove models from the pool to control what appears here.
          Falls back to the curated Oracle catalog when the pool is empty.
        </p>
      </header>

      {MODEL_ROLES.map((role) => (
        <Card key={role.settingKey} className="max-w-2xl">
          <CardHeader>
            <CardTitle className="text-base">{role.title}</CardTitle>
            <CardDescription className="font-medium text-foreground/70">
              {role.subtitle}
            </CardDescription>
            <p className="text-sm text-muted-foreground mt-1">
              {role.description}
            </p>
            <RequiredCapIcons keys={role.requiredCaps} />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {role.requirements.map((req) => (
                <span
                  key={req}
                  className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground"
                >
                  {req}
                </span>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            <ModelPicker
              currentModel={currentValues[role.settingKey] ?? null}
              settingKey={role.settingKey}
              settingDescription={role.settingDescription}
              requiredCaps={role.requiredCaps}
            />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
