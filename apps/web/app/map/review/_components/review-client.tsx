'use client';

// Admin review list (issue #255): every open mark-as-wrong flag with its
// item, note and a resolve action. G1: resolving REQUIRES choosing an action
// — the write creates a cmap.correction row keyed by content, so the verdict
// survives rebuilds.

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { brainGet, brainPost, type ReviewFlag } from '../../_components/brain';
import { LoadState } from '../../_components/bits';

const ACTIONS = [
  'reject',
  'edit',
  'confirm',
  'merge',
  'split',
  'rename',
  'reassign',
] as const;

function itemHref(flag: ReviewFlag): string | null {
  if (flag.item_type === 'entity') return `/map/entity/${flag.item_id}`;
  if (flag.item_type === 'community') return `/map/community/${flag.item_id}`;
  return null;
}

function FlagRow({
  flag,
  busy,
  onResolve,
}: {
  flag: ReviewFlag;
  busy: boolean;
  onResolve: (
    flag: ReviewFlag,
    action: string,
    reason: string,
    payload: string,
  ) => void;
}) {
  const [action, setAction] = useState('');
  const [reason, setReason] = useState('');
  const [payload, setPayload] = useState('');
  const href = itemHref(flag);
  return (
    <div
      data-testid="review-flag"
      data-item-type={flag.item_type}
      className="flex flex-wrap items-start justify-between gap-2 rounded border p-3"
    >
      <div className="space-y-1">
        <p className="text-sm">
          <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium uppercase">
            {flag.item_type}
          </span>
          {href ? (
            <Link href={href} className="underline">
              {flag.label}
            </Link>
          ) : (
            <span>{flag.label}</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground" data-testid="review-item-id">
          {flag.item_id}
        </p>
        <p className="text-sm" data-testid="review-note">
          {flag.note ?? <span className="text-muted-foreground">No note</span>}
        </p>
        <p className="text-xs text-muted-foreground">
          Marked {flag.created_at ? flag.created_at.slice(0, 10) : '—'}
        </p>
      </div>
      <div className="flex flex-col items-stretch gap-2">
        <select
          data-testid="review-action"
          aria-label="Resolve action"
          className="h-8 rounded border bg-background px-2 text-sm"
          value={action}
          onChange={(event) => setAction(event.target.value)}
        >
          <option value="" disabled>
            Choose an action…
          </option>
          {ACTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <input
          data-testid="review-reason"
          className="h-8 rounded border bg-background px-2 text-sm"
          placeholder="Why (optional)"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <input
          data-testid="review-payload"
          className="h-8 rounded border bg-background px-2 text-sm"
          placeholder='Payload JSON — edit / rename {"name": …} / merge {"pair": …}'
          value={payload}
          onChange={(event) => setPayload(event.target.value)}
        />
        <Button
          data-testid="review-resolve"
          size="sm"
          variant="outline"
          disabled={busy || action === ''}
          onClick={() => onResolve(flag, action, reason, payload)}
        >
          {busy ? 'Resolving…' : 'Resolve'}
        </Button>
      </div>
    </div>
  );
}

export function ReviewClient() {
  const [flags, setFlags] = useState<ReviewFlag[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const body = await brainGet<{ flags: ReviewFlag[] }>('flags');
      setFlags(body.flags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'load failed');
    }
  }, []);

  useEffect(() => {
    async function load() {
      await refresh();
    }
    void load();
  }, [refresh]);

  const resolve = useCallback(
    async (flag: ReviewFlag, action: string, reason: string, payload: string) => {
      setBusy(flag.id);
      try {
        let parsed: unknown = null;
        if (payload.trim()) {
          parsed = JSON.parse(payload);
          if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('payload must be a JSON object');
          }
        }
        await brainPost(`flags/${flag.id}/resolve`, {
          action,
          reason: reason.trim() || null,
          payload: parsed,
        });
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'resolve failed');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  return (
    <div data-testid="review-flags" className="space-y-2">
      <LoadState error={error} loading={flags === null} />
      {flags !== null && flags.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing marked wrong.</p>
      )}
      {flags !== null &&
        flags.map((flag) => (
          <FlagRow
            key={flag.id}
            flag={flag}
            busy={busy === flag.id}
            onResolve={(target, action, reason, payload) =>
              void resolve(target, action, reason, payload)
            }
          />
        ))}
    </div>
  );
}
