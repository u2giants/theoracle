'use client';

// Admin "Mark as wrong" control (issue #255): flags an entity, a projected
// relation edge or a community in cmap.review_flag through the brain proxy.
// Non-admins never see it; an open flag is shown on later visits too.

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { brainGet, brainPost, type ReviewFlag } from './brain';

export type FlagItemType = 'entity' | 'relation' | 'community';

export function relationItemId(fromId: string, toId: string, relType: string): string {
  return `${fromId}:${toId}:${relType}`;
}

export function MarkWrongButton({
  isAdmin,
  itemType,
  itemId,
}: {
  isAdmin: boolean;
  itemType: FlagItemType;
  itemId: string;
}) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [flag, setFlag] = useState<ReviewFlag | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    brainGet<{ flags: ReviewFlag[] }>(
      `flags?item_type=${itemType}&item_id=${encodeURIComponent(itemId)}`,
    )
      .then((body) => {
        if (!cancelled) setFlag(body.flags[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setFlag(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin, itemType, itemId]);

  if (!isAdmin || flag === undefined) return null;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const body = await brainPost<{ flag: ReviewFlag }>('flags', {
        item_type: itemType,
        item_id: itemId,
        note: note.trim() || null,
      });
      setFlag(body.flag);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <span
      data-testid="mark-wrong"
      data-item-type={itemType}
      data-item-id={itemId}
      className="inline-flex flex-wrap items-center gap-1"
    >
      {flag !== null ? (
        <span data-testid="mark-wrong-flagged" className="text-xs text-red-700">
          Flagged as wrong{flag.note ? `: ${flag.note}` : ''}
        </span>
      ) : open ? (
        <>
          <Input
            data-testid="mark-wrong-note"
            className="h-7 w-56 text-xs"
            placeholder="What is wrong? (optional)"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !busy) void submit();
            }}
          />
          <Button
            data-testid="mark-wrong-save"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void submit()}
          >
            {busy ? 'Saving…' : 'Save'}
          </Button>
          <Button
            data-testid="mark-wrong-cancel"
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => {
              setOpen(false);
              setError(null);
            }}
          >
            Cancel
          </Button>
          {error && (
            <span data-testid="mark-wrong-error" className="text-xs text-red-700">
              {error}
            </span>
          )}
        </>
      ) : (
        <Button
          data-testid="mark-wrong-button"
          size="sm"
          variant="outline"
          className="border-red-200 text-red-700 hover:bg-red-50"
          onClick={() => setOpen(true)}
        >
          Mark as wrong
        </Button>
      )}
    </span>
  );
}
