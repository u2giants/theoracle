'use client';

// Admin review list (issue #255): every open mark-as-wrong flag with its
// item, note and a resolve action.

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { brainGet, brainPost, type ReviewFlag } from '../../_components/brain';
import { LoadState } from '../../_components/bits';

function itemHref(flag: ReviewFlag): string | null {
  if (flag.item_type === 'entity') return `/map/entity/${flag.item_id}`;
  if (flag.item_type === 'community') return `/map/community/${flag.item_id}`;
  return null;
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
    void refresh();
  }, [refresh]);

  async function resolve(flag: ReviewFlag) {
    setBusy(flag.id);
    try {
      await brainPost(`flags/${flag.id}/resolve`, {});
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'resolve failed');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div data-testid="review-flags" className="space-y-2">
      <LoadState error={error} loading={flags === null} />
      {flags !== null && flags.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing marked wrong.</p>
      )}
      {flags !== null &&
        flags.map((flag) => {
          const href = itemHref(flag);
          return (
            <div
              key={flag.id}
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
              <Button
                data-testid="review-resolve"
                size="sm"
                variant="outline"
                disabled={busy !== null}
                onClick={() => void resolve(flag)}
              >
                {busy === flag.id ? 'Resolving…' : 'Resolve'}
              </Button>
            </div>
          );
        })}
    </div>
  );
}
