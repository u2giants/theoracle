'use client';

// R10.5 — One proposal card. Compact summary + structured payload preview
// + approve/reject controls (when pending).

import { useState, useTransition } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  approveTaxonomyProposal,
  rejectTaxonomyProposal,
} from '../../_actions';

type ProposalCardProps = {
  proposal: {
    id: string;
    proposal_type: string;
    payload: unknown;
    status: string;
    reviewed_at: string | null;
    created_at: string;
    reviewer_name: string | null;
  };
};

type ProposalPayload = {
  proposedId?: string;
  proposedName?: string;
  oneSentencePurpose?: string;
  proposalReason?: string;
  boundaryRules?: {
    belongsHere?: string[];
    doesNotBelongHere?: string[];
    commonEntityHints?: Array<{ entityType: string; canonicalValue: string }>;
    defaultExcludedDocumentClasses?: string[];
    neighboringDomainIds?: string[];
  };
  representativeEvidence?: Array<{
    sourceType: string;
    sourceId: string;
    shortSnippet: string;
    whyRepresentative?: string;
  }>;
  affectedCounts?: Record<string, number>;
  suggestedRetrievalExclusions?: string[];
  recommendedAction?: string;
  recommendedActionReason?: string;
  confidence?: number;
  rollbackPreview?: string;
};

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
  };
  return map[status] ?? 'bg-muted';
}

export function ProposalCard({ proposal }: ProposalCardProps) {
  const payload = (proposal.payload ?? {}) as ProposalPayload;
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState('');

  const onApprove = () => {
    setError(null);
    startTransition(async () => {
      try {
        await approveTaxonomyProposal(proposal.id, note.trim() || null);
        setNote('');
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    });
  };

  const onReject = () => {
    if (!note.trim()) {
      setError('A rejection reason is required.');
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        await rejectTaxonomyProposal(proposal.id, note.trim());
        setNote('');
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    });
  };

  const isPendingReview = proposal.status === 'pending';
  const evidence = payload.representativeEvidence ?? [];
  const entityHints = payload.boundaryRules?.commonEntityHints ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            <span className="font-mono text-xs text-muted-foreground">
              {proposal.proposal_type}
            </span>{' '}
            {payload.proposedName ?? '(unnamed)'}
            {payload.proposedId && (
              <span className="ml-2 font-mono text-xs text-muted-foreground">
                ({payload.proposedId})
              </span>
            )}
          </CardTitle>
          <span className={`rounded px-1.5 py-0.5 text-xs ${statusBadge(proposal.status)}`}>
            {proposal.status}
          </span>
        </div>
        {payload.oneSentencePurpose && (
          <p className="mt-1 text-sm">{payload.oneSentencePurpose}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {payload.proposalReason && (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Why proposed
            </div>
            <div className="italic">{payload.proposalReason}</div>
          </div>
        )}

        {payload.boundaryRules?.belongsHere && payload.boundaryRules.belongsHere.length > 0 && (
          <ChipList
            label="Belongs here"
            tone="green"
            items={payload.boundaryRules.belongsHere}
          />
        )}
        {payload.boundaryRules?.doesNotBelongHere &&
          payload.boundaryRules.doesNotBelongHere.length > 0 && (
            <ChipList
              label="Does NOT belong here"
              tone="red"
              items={payload.boundaryRules.doesNotBelongHere}
            />
          )}
        {entityHints.length > 0 && (
          <ChipList
            label="Common entities"
            tone="neutral"
            items={entityHints.map((e) => `${e.entityType}: ${e.canonicalValue}`)}
          />
        )}
        {payload.boundaryRules?.defaultExcludedDocumentClasses &&
          payload.boundaryRules.defaultExcludedDocumentClasses.length > 0 && (
            <ChipList
              label="Default excluded document classes"
              tone="amber"
              items={payload.boundaryRules.defaultExcludedDocumentClasses}
            />
          )}
        {payload.boundaryRules?.neighboringDomainIds &&
          payload.boundaryRules.neighboringDomainIds.length > 0 && (
            <ChipList
              label="Neighboring domains"
              tone="neutral"
              items={payload.boundaryRules.neighboringDomainIds}
            />
          )}

        {evidence.length > 0 && (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Representative evidence ({evidence.length})
            </div>
            <ul className="space-y-1">
              {evidence.slice(0, 5).map((e, i) => (
                <li key={i} className="rounded border-l-2 border-muted bg-muted/30 px-2 py-1">
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {e.sourceType}:{e.sourceId.slice(0, 8)}…
                  </span>
                  <div className="mt-0.5 italic">"{e.shortSnippet}"</div>
                  {e.whyRepresentative && (
                    <div className="text-[10px] text-muted-foreground">{e.whyRepresentative}</div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {payload.affectedCounts && Object.keys(payload.affectedCounts).length > 0 && (
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              Affected counts
            </div>
            <div className="flex gap-2 text-xs">
              {Object.entries(payload.affectedCounts).map(([k, v]) => (
                <span key={k} className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">
                  {k}: {v}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between border-t pt-2 text-[10px] text-muted-foreground">
          <span>
            Created {new Date(proposal.created_at).toLocaleString()}
            {proposal.reviewer_name && proposal.reviewed_at && (
              <>
                {' '}
                · Reviewed by <strong>{proposal.reviewer_name}</strong>{' '}
                {new Date(proposal.reviewed_at).toLocaleString()}
              </>
            )}
          </span>
          {payload.recommendedAction && (
            <span>
              Recommended:{' '}
              <strong className="text-foreground">{payload.recommendedAction}</strong>
              {payload.confidence != null && ` (conf ${payload.confidence.toFixed(2)})`}
            </span>
          )}
        </div>

        {isPendingReview && (
          <div className="space-y-2 border-t pt-3">
            <Input
              type="text"
              placeholder="Reviewer note (required for reject; optional for approve)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
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
                {isPending ? 'Working…' : 'Approve'}
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

function ChipList({
  label,
  tone,
  items,
}: {
  label: string;
  tone: 'green' | 'red' | 'amber' | 'neutral';
  items: string[];
}) {
  const colorMap: Record<typeof tone, string> = {
    green: 'bg-green-50 text-green-800',
    red: 'bg-red-50 text-red-800',
    amber: 'bg-amber-50 text-amber-800',
    neutral: 'bg-muted text-muted-foreground',
  };
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="flex flex-wrap gap-1">
        {items.map((it, i) => (
          <span key={`${label}-${i}`} className={`rounded px-1.5 py-0.5 ${colorMap[tone]}`}>
            {it}
          </span>
        ))}
      </div>
    </div>
  );
}
