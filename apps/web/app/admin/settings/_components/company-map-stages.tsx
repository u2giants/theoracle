'use client';

// Company Map model stages — the primary block of the admin model pages.
// Each stage shows the three best models from the 2026-11-03 bake-off with a
// relative score, OpenRouter pricing and a tooltip, and lets an admin pick the
// one the brain uses (PUT /api/brain/models/<stage> → cmap.model_seat). The
// live seat comes from the brain's GET /models; without a page choice the
// brain falls back to its Coolify env seat.

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Copy, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { COMPANY_MAP_STAGES, type CompanyMapStage, type CompanyMapModels } from './stage-briefs';
import { PRICES_AS_OF, STAGE_CANDIDATES, type StageCandidate } from './stage-candidates';

const money = (v: number) => `$${v < 0.1 ? v.toFixed(3) : v.toFixed(2)}`;

function priceLabel(c: StageCandidate): string {
  return c.priceOut == null
    ? `${money(c.priceIn)} / 1M tokens`
    : `${money(c.priceIn)} in · ${money(c.priceOut)} out / 1M tokens`;
}

function CandidateRow({
  candidate,
  relative,
  isLive,
  busy,
  onPick,
}: {
  candidate: StageCandidate;
  relative: number;
  isLive: boolean;
  busy: boolean;
  onPick: () => void;
}) {
  return (
    <li
      className={cn(
        'rounded-md border px-3 py-2 flex items-center gap-3',
        isLive ? 'border-primary bg-primary/5' : 'border-border',
      )}
    >
      <div className="w-12 shrink-0 text-center">
        <div className="text-base font-semibold tabular-nums leading-none">{relative}</div>
        <div className="text-[10px] text-muted-foreground mt-0.5">score</div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-mono text-xs break-all">{candidate.model}</span>
          {candidate.recommended && (
            <span className="rounded-full bg-amber-100 text-amber-900 dark:bg-amber-950/50 dark:text-amber-200 px-1.5 py-0.5 text-[10px] font-medium">
              Bake-off winner
            </span>
          )}
          <span className="relative group inline-flex">
            <button
              type="button"
              aria-label={`What ${candidate.model} did well and badly`}
              className="text-muted-foreground hover:text-foreground focus:text-foreground"
            >
              <Info className="size-3.5" />
            </button>
            <span
              role="tooltip"
              className="invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 transition-opacity absolute z-20 left-1/2 -translate-x-1/2 top-5 w-72 max-w-[80vw] rounded-md border bg-popover text-popover-foreground shadow-md p-3 text-xs leading-relaxed space-y-1.5"
            >
              <span className="block">
                <span className="font-medium">Did well: </span>
                {candidate.good}
              </span>
              <span className="block">
                <span className="font-medium">Did badly: </span>
                {candidate.weak}
              </span>
              <span className="block">
                <span className="font-medium">Compared with the top scorer: </span>
                {candidate.vsBest}
              </span>
            </span>
          </span>
        </div>
        <div className="text-[11px] text-muted-foreground mt-0.5 tabular-nums">
          {priceLabel(candidate)}
        </div>
      </div>
      {isLive ? (
        <span className="flex items-center gap-1 text-xs font-medium text-primary shrink-0">
          <Check className="size-3.5" /> In use
        </span>
      ) : (
        <button
          type="button"
          onClick={onPick}
          disabled={busy}
          className="shrink-0 rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Use this'}
        </button>
      )}
    </li>
  );
}

function StageCard({
  stage,
  liveModel,
  note,
}: {
  stage: CompanyMapStage;
  liveModel: string | null;
  note?: string;
}) {
  const router = useRouter();
  const [briefCopied, setBriefCopied] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seat, setSeat] = useState<string | null>(liveModel);
  const candidates = STAGE_CANDIDATES[stage.id];
  const best = Math.max(...candidates.map((c) => c.quality));
  const liveListed = candidates.some((c) => c.model === seat);

  async function pick(model: string) {
    setBusy(model);
    setError(null);
    try {
      const res = await fetch(`/api/brain/models/${stage.id}`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ model }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string; error?: string };
        throw new Error(body.detail ?? body.error ?? `Save failed (${res.status})`);
      }
      setSeat(model);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(null);
    }
  }

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
    <div className="rounded-lg border bg-card px-4 py-3 space-y-2">
      <div>
        <h3 className="text-sm font-semibold leading-tight">
          <span className="font-normal text-muted-foreground">{stage.order}.</span> {stage.title}
        </h3>
        <p className="text-xs text-muted-foreground leading-relaxed mt-1">{stage.role}</p>
      </div>

      <ul className="space-y-1.5">
        {candidates.map((c) => (
          <CandidateRow
            key={c.model}
            candidate={c}
            relative={Math.round((c.quality / best) * 100)}
            isLive={c.model === seat}
            busy={busy === c.model}
            onPick={() => pick(c.model)}
          />
        ))}
      </ul>

      {!liveListed && (
        <p className="text-[11px] text-muted-foreground">
          In use now: <span className="font-mono">{seat ?? 'not configured'}</span> (not one of the
          top three)
        </p>
      )}
      {note && <p className="text-[11px] text-muted-foreground">{note}</p>}
      {error && <p className="text-[11px] text-red-600">{error}</p>}

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
          The nine AI jobs in the Company Map, in pipeline order. Each shows the three best models
          from the {PRICES_AS_OF} bake-off on our real documents. Score is relative to the best
          model for that job (100 = best); hover the info icon for what each did well and badly.
          Prices are OpenRouter list prices as of {PRICES_AS_OF}. A choice takes effect on the next
          run.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {COMPANY_MAP_STAGES.map((stage) => (
          <StageCard
            key={stage.id}
            stage={stage}
            liveModel={models ? models[stage.modelKey] : null}
            note={
              stage.id === 'flat'
                ? `Cheap first pass runs on ScaleDown (${models?.scaledown_enabled ? 'on' : 'off'}); this model handles what ScaleDown cannot.`
                : stage.id === 'embed'
                  ? 'Changing this re-indexes every stored passage, name and item with the new model.'
                  : undefined
            }
          />
        ))}
      </div>
    </section>
  );
}
