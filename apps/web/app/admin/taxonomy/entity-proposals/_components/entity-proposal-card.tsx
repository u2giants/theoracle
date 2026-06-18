'use client';

// R10.5 — Entity-proposal card with approve/reject controls.

import { useState, useTransition } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { formatNYDateTime } from '@/lib/time';
import {
  approveEntityProposal,
  rejectEntityProposal,
} from '../../_actions';

type EntityProposalCardProps = {
  proposal: {
    id: string;
    proposed_entity_type: string;
    proposed_canonical_value: string;
    raw_strings_observed: unknown;
    proposed_aliases: unknown;
    proposed_domain_hints: unknown;
    observed_in_source_type: string;
    observed_in_source_id: string | null;
    status: string;
    reviewed_at: string | null;
    created_at: string;
    reviewer_name: string | null;
  };
};

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    merged_into_existing: 'bg-blue-100 text-blue-800',
    rejected: 'bg-red-100 text-red-800',
  };
  return map[status] ?? 'bg-muted';
}

export function EntityProposalCard({ proposal }: EntityProposalCardProps) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [finalValue, setFinalValue] = useState(proposal.proposed_canonical_value);
  const [displayLabel, setDisplayLabel] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  const isPendingReview = proposal.status === 'pending';
  const rawStrings = Array.isArray(proposal.raw_strings_observed)
    ? (proposal.raw_strings_observed as string[])
    : [];
  const aliases = Array.isArray(proposal.proposed_aliases)
    ? (proposal.proposed_aliases as string[])
    : [];
  const domainHints = Array.isArray(proposal.proposed_domain_hints)
    ? (proposal.proposed_domain_hints as string[])
    : [];

  const onApprove = () => {
    if (!finalValue.trim()) {
      setError('Canonical value cannot be empty.');
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        await approveEntityProposal(
          proposal.id,
          finalValue.trim(),
          displayLabel.trim() || undefined,
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    });
  };

  const onReject = () => {
    if (!rejectReason.trim()) {
      setError('A rejection reason is required.');
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        await rejectEntityProposal(proposal.id, rejectReason.trim());
        setRejectReason('');
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    });
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            <span className="font-mono text-xs text-muted-foreground">
              {proposal.proposed_entity_type}
            </span>{' '}
            {proposal.proposed_canonical_value}
          </CardTitle>
          <span className={`rounded px-1.5 py-0.5 text-xs ${statusBadge(proposal.status)}`}>
            {proposal.status}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-3">
          <Field
            label="Observed in"
            value={
              <>
                {proposal.observed_in_source_type}
                {proposal.observed_in_source_id && (
                  <span className="ml-1 font-mono text-muted-foreground">
                    {proposal.observed_in_source_id.slice(0, 8)}…
                  </span>
                )}
              </>
            }
          />
          <Field
            label="Created"
            value={formatNYDateTime(proposal.created_at)}
          />
          {proposal.reviewer_name && proposal.reviewed_at && (
            <Field
              label="Reviewed by"
              value={
                <>
                  {proposal.reviewer_name}{' '}
                  <span className="text-muted-foreground">
                    {formatNYDateTime(proposal.reviewed_at)}
                  </span>
                </>
              }
            />
          )}
        </dl>

        {rawStrings.length > 0 && (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Raw strings observed
            </div>
            <div className="flex flex-wrap gap-1">
              {rawStrings.map((s, i) => (
                <span key={i} className="rounded bg-muted px-1.5 py-0.5 font-mono">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {aliases.length > 0 && (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Proposed aliases
            </div>
            <div className="flex flex-wrap gap-1">
              {aliases.map((a, i) => (
                <span key={i} className="rounded bg-muted px-1.5 py-0.5 font-mono">
                  {a}
                </span>
              ))}
            </div>
          </div>
        )}

        {domainHints.length > 0 && (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Proposed domain hints
            </div>
            <div className="flex flex-wrap gap-1">
              {domainHints.map((d, i) => (
                <span key={i} className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-blue-800">
                  {d}
                </span>
              ))}
            </div>
          </div>
        )}

        {isPendingReview && (
          <div className="space-y-2 border-t pt-3">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Final canonical value
                </label>
                <Input
                  type="text"
                  value={finalValue}
                  onChange={(e) => setFinalValue(e.target.value)}
                  className="mt-1 text-xs"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Display label (optional)
                </label>
                <Input
                  type="text"
                  value={displayLabel}
                  onChange={(e) => setDisplayLabel(e.target.value)}
                  placeholder="Same as canonical if blank"
                  className="mt-1 text-xs"
                />
              </div>
            </div>
            <Input
              type="text"
              placeholder="Rejection reason (required to reject)"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="text-xs"
            />
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                onClick={onApprove}
                disabled={isPending}
                className="bg-green-700 hover:bg-green-800"
              >
                {isPending ? 'Working…' : 'Approve / create entity'}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onReject}
                disabled={isPending}
              >
                Reject
              </Button>
            </div>
            {error && (
              <div className="rounded bg-red-50 px-2 py-1 text-xs text-red-800">{error}</div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}
