'use client';

// Admin toggle for settings.extraction_dispatch_mode.
// Posts to /api/admin/settings on change. Confirms before flipping to 'batch'
// because the change introduces an up-to-24-hour delay between message arrival
// and claim extraction (provider Batch API SLA — D14).

import { useState } from 'react';
import { cn } from '@/lib/utils';

export type DispatchMode = 'sync' | 'batch';

const SETTING_KEY = 'extraction_dispatch_mode';
const SETTING_DESCRIPTION =
  'sync | batch — D14 provider Batch API dispatch for claim extraction.';

type Status = 'idle' | 'saving' | 'saved' | 'error';

interface DispatchModeToggleProps {
  currentMode: DispatchMode;
}

export function DispatchModeToggle({ currentMode }: DispatchModeToggleProps) {
  const [mode, setMode] = useState<DispatchMode>(currentMode);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);

  async function selectMode(next: DispatchMode) {
    if (next === mode) return;
    if (next === 'batch') {
      const confirmed = window.confirm(
        'Switching to BATCH mode.\n\n' +
          '• Claim extraction will run via the provider Batch API (~50% off).\n' +
          '• Newly sent messages will not appear in the claims table for up to 24 hours.\n' +
          '• Within a single chat session, the Oracle still reads live message history, so conversation quality is unchanged.\n' +
          '• Cross-session knowledge freshness drops by up to 24 hours.\n' +
          '• Vertex extraction routes additionally require GOOGLE_VERTEX_BATCH_GCS_BUCKET.\n\n' +
          'Flip back to sync any time — the next cron tick respects the new value.\n\n' +
          'Continue?',
      );
      if (!confirmed) return;
    }

    setStatus('saving');
    setError(null);
    try {
      const res = await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: SETTING_KEY,
          value: next,
          description: SETTING_DESCRIPTION,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      setMode(next);
      setStatus('saved');
      setTimeout(() => setStatus('idle'), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus('error');
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <ModeOption
          value="sync"
          active={mode === 'sync'}
          onClick={() => selectMode('sync')}
          title="Sync"
          subtitle="Real-time API"
          bullets={[
            'Claims appear in the DB within minutes of message arrival',
            'Full sync API pricing',
            'No GCS bucket needed for Vertex',
          ]}
        />
        <ModeOption
          value="batch"
          active={mode === 'batch'}
          onClick={() => selectMode('batch')}
          title="Batch"
          subtitle="Provider Batch API · ~50% off"
          bullets={[
            'Up to 24-hour delay before claims appear in the DB',
            '~50% lower input/output token cost',
            'Vertex routes require GOOGLE_VERTEX_BATCH_GCS_BUCKET',
          ]}
        />
      </div>

      <div className="flex items-center gap-3 text-sm">
        {status === 'saving' && <span className="text-muted-foreground">Saving…</span>}
        {status === 'saved' && <span className="text-green-600">Saved.</span>}
        {status === 'error' && error && <span className="text-destructive">{error}</span>}
        {status === 'idle' && (
          <span className="text-xs text-muted-foreground">
            Current: <strong className="text-foreground">{mode}</strong>. Read every cron tick — flipping does not require a redeploy.
          </span>
        )}
      </div>
    </div>
  );
}

function ModeOption({
  value,
  active,
  onClick,
  title,
  subtitle,
  bullets,
}: {
  value: DispatchMode;
  active: boolean;
  onClick: () => void;
  title: string;
  subtitle: string;
  bullets: string[];
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'text-left rounded-md border p-3 transition-colors',
        active
          ? 'border-primary bg-primary/5 ring-1 ring-primary/40'
          : 'border-input hover:bg-muted/40',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium text-sm">{title}</div>
          <div className="text-xs text-muted-foreground">{subtitle}</div>
        </div>
        <div
          className={cn(
            'size-4 rounded-full border flex items-center justify-center mt-0.5 shrink-0',
            active ? 'border-primary' : 'border-muted-foreground/40',
          )}
        >
          {active && <div className="size-2 rounded-full bg-primary" />}
        </div>
      </div>
      <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
        {bullets.map((b, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <span className="text-muted-foreground/60 shrink-0">•</span>
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <input type="radio" name="dispatch-mode" value={value} checked={active} readOnly className="sr-only" />
    </button>
  );
}
