'use client';

// Company Map model stages — the primary block of the admin model page.
// Read-only seat display: the live model ids come from the brain's GET /models
// (env seats in Coolify app oracle-brain); each card copies its job brief.

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  COMPANY_MAP_STAGES,
  SEAT_CHIP_LABELS,
  SEAT_CHIP_NOTES,
  SEAT_CHIP_STYLES,
  type CompanyMapStage,
  type CompanyMapModels,
  type SeatChip,
} from './stage-briefs';

const CHIP_ORDER: SeatChip[] = ['incumbent', 'assigned', 'bakeoff', 'frozen'];

function StageCard({
  stage,
  models,
}: {
  stage: CompanyMapStage;
  models: CompanyMapModels | null;
}) {
  const [briefCopied, setBriefCopied] = useState(false);
  const modelId = models ? models[stage.modelKey] : null;

  async function copyBrief() {
    try {
      await navigator.clipboard.writeText(stage.brief);
      setBriefCopied(true);
      setTimeout(() => setBriefCopied(false), 2500);
    } catch {
      // Clipboard API unavailable (insecure context / denied) — no-op.
    }
  }

  return (
    <div className="rounded-lg border bg-card px-4 py-3 space-y-1.5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold leading-tight">
          <span className="font-normal text-muted-foreground">{stage.order}.</span>{' '}
          {stage.title}
        </h3>
        <span
          className={cn(
            'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
            SEAT_CHIP_STYLES[stage.chip],
          )}
        >
          {SEAT_CHIP_LABELS[stage.chip]}
        </span>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">{stage.role}</p>

      <div className="space-y-0.5">
        <p className="font-mono text-xs text-foreground">
          {modelId ?? (
            <span className="font-sans italic text-muted-foreground">not configured</span>
          )}
        </p>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          <span className="font-mono">{stage.envVar}</span>
          {stage.envNote ? ` · ${stage.envNote}` : ''}
          {stage.id === 'embed' && models?.embed_dims != null
            ? ` · dims ${models.embed_dims} (BRAIN_EMBED_DIMS)`
            : ''}
          {' · set in Coolify app oracle-brain'}
        </p>
        {stage.id === 'flat' && models && (
          <p className="text-[11px] text-muted-foreground">
            ScaleDown:{' '}
            {models.scaledown_enabled
              ? 'enabled'
              : 'disabled (frontier fallback only)'}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={copyBrief}
        title="Copy this stage's role brief — what it's fed, what's expected, and how to evaluate a candidate — to your clipboard"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {briefCopied ? (
          <Check className="size-3.5 text-green-600" />
        ) : (
          <Copy className="size-3.5" />
        )}
        {briefCopied ? 'Copied' : 'Copy job brief'}
      </button>
    </div>
  );
}

export function CompanyMapStages({ models }: { models: CompanyMapModels | null }) {
  return (
    <section className="max-w-5xl space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Company Map model stages</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          The nine model-touching stages of the Company Map pipeline, in
          pipeline order. Each card copies its job brief. Seats come from the
          brain service env — <span className="font-mono text-xs">not configured</span>{' '}
          means the variable is unset or the brain is unreachable.
        </p>
      </div>

      {/* One page-level legend for the seat-status chips. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Seat status</span>
        {CHIP_ORDER.map((chip) => (
          <span key={chip} className="flex items-center gap-1.5">
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
                SEAT_CHIP_STYLES[chip],
              )}
            >
              {SEAT_CHIP_LABELS[chip]}
            </span>
            <span>{SEAT_CHIP_NOTES[chip]}</span>
          </span>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {COMPANY_MAP_STAGES.map((stage) => (
          <StageCard key={stage.id} stage={stage} models={models} />
        ))}
      </div>
    </section>
  );
}
