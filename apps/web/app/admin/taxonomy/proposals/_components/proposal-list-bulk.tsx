'use client';

// Wraps the proposal list with checkbox multi-select and a sticky bulk-action bar.

import { useState, useTransition } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  bulkApproveTaxonomyProposals,
  bulkRejectTaxonomyProposals,
} from '../../_actions';
import { ProposalCard } from './proposal-card';

type ProposalRow = {
  id: string;
  proposal_type: string;
  payload: unknown;
  status: string;
  reviewed_at: string | null;
  created_at: string;
  reviewer_name: string | null;
};

export function ProposalListBulk({ proposals }: { proposals: ProposalRow[] }) {
  const pending = proposals.filter((p) => p.status === 'pending');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkNote, setBulkNote] = useState('');
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [bulkResult, setBulkResult] = useState<string | null>(null);
  const [isBusy, startTransition] = useTransition();

  const allPendingIds = pending.map((p) => p.id);
  const allSelected = allPendingIds.length > 0 && allPendingIds.every((id) => selected.has(id));

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allPendingIds));
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearBulk() {
    setSelected(new Set());
    setBulkNote('');
    setBulkError(null);
    setBulkResult(null);
  }

  function onBulkApprove() {
    setBulkError(null);
    setBulkResult(null);
    startTransition(async () => {
      const ids = [...selected];
      const res = await bulkApproveTaxonomyProposals(ids, bulkNote.trim() || null);
      if (res.errors.length > 0) {
        setBulkError(`${res.approved} approved; ${res.errors.length} failed: ${res.errors.map((e) => e.error).join(', ')}`);
      } else {
        setBulkResult(`${res.approved} proposal${res.approved !== 1 ? 's' : ''} approved.`);
      }
      clearBulk();
    });
  }

  function onBulkReject() {
    if (!bulkNote.trim()) {
      setBulkError('A rejection reason is required.');
      return;
    }
    setBulkError(null);
    setBulkResult(null);
    startTransition(async () => {
      const ids = [...selected];
      const res = await bulkRejectTaxonomyProposals(ids, bulkNote.trim());
      if (res.errors.length > 0) {
        setBulkError(`${res.rejected} rejected; ${res.errors.length} failed: ${res.errors.map((e) => e.error).join(', ')}`);
      } else {
        setBulkResult(`${res.rejected} proposal${res.rejected !== 1 ? 's' : ''} rejected.`);
      }
      clearBulk();
    });
  }

  return (
    <div className="space-y-3">
      {/* Bulk-select header — only shown when there are pending proposals */}
      {pending.length > 0 && (
        <div className="flex items-center gap-3 rounded border bg-muted/40 px-3 py-2 text-sm">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            aria-label="Select all pending proposals"
            className="h-4 w-4 cursor-pointer"
          />
          <span className="text-muted-foreground">
            {selected.size > 0
              ? `${selected.size} of ${pending.length} pending selected`
              : `Select all ${pending.length} pending`}
          </span>
          {selected.size > 0 && (
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="ml-auto text-xs text-muted-foreground underline"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* Sticky bulk-action bar */}
      {selected.size > 0 && (
        <div className="sticky top-2 z-10 rounded border bg-background shadow-md px-3 py-2 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <Input
              type="text"
              placeholder="Note / reason (required for reject)"
              value={bulkNote}
              onChange={(e) => setBulkNote(e.target.value)}
              className="h-8 flex-1 min-w-40 text-xs"
            />
            <Button
              size="sm"
              onClick={onBulkApprove}
              disabled={isBusy}
              className="bg-green-700 hover:bg-green-800 h-8 text-xs"
            >
              {isBusy ? 'Working…' : `Approve ${selected.size}`}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onBulkReject}
              disabled={isBusy}
              className="h-8 text-xs"
            >
              {isBusy ? 'Working…' : `Reject ${selected.size}`}
            </Button>
          </div>
          {bulkError && (
            <div className="rounded bg-red-50 px-2 py-1 text-xs text-red-800">{bulkError}</div>
          )}
        </div>
      )}

      {bulkResult && (
        <div className="rounded bg-green-50 px-3 py-2 text-xs text-green-800">{bulkResult}</div>
      )}

      {/* Individual cards */}
      {proposals.map((p) => (
        <div key={p.id} className="flex items-start gap-2">
          {p.status === 'pending' && (
            <input
              type="checkbox"
              checked={selected.has(p.id)}
              onChange={() => toggleOne(p.id)}
              aria-label={`Select proposal ${p.id}`}
              className="mt-4 h-4 w-4 flex-shrink-0 cursor-pointer"
            />
          )}
          <div className={p.status === 'pending' ? 'flex-1' : 'flex-1 ml-6'}>
            <ProposalCard proposal={p} />
          </div>
        </div>
      ))}
    </div>
  );
}
