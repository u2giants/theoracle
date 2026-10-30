'use client';

import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { sourceHref, type SourceRef } from './brain';

// Stance colours from plan step 10: policy=blue, practice=green,
// report=amber, inference=grey.
const STANCE_STYLES: Record<string, string> = {
  policy: 'bg-blue-100 text-blue-900',
  practice: 'bg-green-100 text-green-900',
  report: 'bg-amber-100 text-amber-900',
  inference: 'bg-gray-200 text-gray-800',
};

export function StanceBadge({ stance }: { stance: string }) {
  return (
    <span
      data-testid="stance-badge"
      data-stance={stance}
      className={cn(
        'inline-block rounded px-1.5 py-0.5 text-xs font-medium',
        STANCE_STYLES[stance] ?? STANCE_STYLES.inference,
      )}
    >
      {stance}
    </span>
  );
}

export function SourceChip({ source, chunkId }: { source: SourceRef; chunkId?: string }) {
  return (
    <Link
      href={sourceHref(source.id, chunkId)}
      data-testid="source-chip"
      className="inline-block max-w-[16rem] truncate rounded-full border px-2 py-0.5 text-xs hover:bg-muted"
      title={source.title}
    >
      {source.title}
    </Link>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose prose-sm max-w-none space-y-2 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mt-3 [&_h2]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}

export function LoadState({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <p className="text-sm text-red-700">Could not load: {error}</p>;
  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  return null;
}
