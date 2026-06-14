'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Info, Paperclip, UploadCloud, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type UploadResult =
  | { fileName: string; ok: true; documentId: string }
  | { fileName: string; ok: false; error: string };

type DomainHint = {
  id: string;
  name: string;
  description: string;
  belongsHere: unknown;
  doesNotBelongHere: unknown;
  commonEntityHints: unknown;
};

function stringList(value: unknown, limit = 3): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).slice(0, limit)
    : [];
}

function entityHintList(value: unknown, limit = 4): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const hint = item as { entityType?: unknown; canonicalValue?: unknown };
      if (typeof hint.canonicalValue !== 'string' || !hint.canonicalValue.trim()) return null;
      return typeof hint.entityType === 'string' && hint.entityType.trim()
        ? `${hint.canonicalValue} (${hint.entityType})`
        : hint.canonicalValue;
    })
    .filter((item): item is string => Boolean(item))
    .slice(0, limit);
}

function tooltipTitle(domain: DomainHint): string {
  const belongsHere = stringList(domain.belongsHere);
  const doesNotBelongHere = stringList(domain.doesNotBelongHere, 2);
  const entityHints = entityHintList(domain.commonEntityHints, 3);
  return [
    domain.description,
    belongsHere.length ? `Use for: ${belongsHere.join('; ')}` : null,
    doesNotBelongHere.length ? `Not for: ${doesNotBelongHere.join('; ')}` : null,
    entityHints.length ? `Common signals: ${entityHints.join('; ')}` : null,
  ]
    .filter(Boolean)
    .join('\n');
}

export function AdminDocumentUpload({
  domains,
}: {
  /** Active knowledge top-domains, for the optional domain-hint chips. */
  domains: DomainHint[];
}) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [results, setResults] = useState<UploadResult[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [context, setContext] = useState('');
  const [hintIds, setHintIds] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  function toggleHint(id: string) {
    setHintIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function addFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
    setStatus('idle');
    setErrorMsg(null);
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function upload() {
    if (files.length === 0) return;
    setStatus('uploading');
    setErrorMsg(null);
    setResults([]);
    try {
      const body = new FormData();
      for (const f of files) body.append('files', f);
      if (context.trim()) body.append('context', context.trim());
      if (hintIds.length > 0) body.append('domainHints', JSON.stringify(hintIds));

      const res = await fetch('/api/admin/documents', { method: 'POST', body });
      const data = (await res.json()) as { ok: boolean; results?: UploadResult[]; error?: string };
      if (!res.ok && !data.results) {
        throw new Error(data.error ?? `Upload failed (${res.status})`);
      }
      setResults(data.results ?? []);
      setStatus(data.ok ? 'done' : 'error');
      setFiles([]);
      setContext('');
      setHintIds([]);
      // Surface the newly-created rows (status pending_processing).
      router.refresh();
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : 'Upload failed.');
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          addFiles(e.dataTransfer.files);
        }}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center text-sm transition-colors',
          dragOver ? 'border-ring bg-accent/40' : 'border-input bg-background',
        )}
      >
        <UploadCloud className="size-6 text-muted-foreground" />
        <div>
          <button
            type="button"
            className="font-medium text-foreground underline underline-offset-2"
            onClick={() => inputRef.current?.click()}
            disabled={status === 'uploading'}
          >
            Choose files
          </button>{' '}
          <span className="text-muted-foreground">or drag and drop</span>
        </div>
        <p className="text-xs text-muted-foreground">
          PDF, Word (.docx), Excel/CSV, plain text, or images (PNG, JPEG, WebP, HEIC).
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="sr-only"
          disabled={status === 'uploading'}
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-1.5 text-sm"
            >
              <Paperclip className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{f.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {(f.size / 1024).toFixed(0)} KB
              </span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="shrink-0 text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${f.name}`}
                disabled={status === 'uploading'}
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Optional context + domain hints — applied to every file in this upload. */}
      <div className="space-y-3 rounded-md border bg-muted/20 p-3">
        <div className="space-y-1">
          <label htmlFor="doc-context" className="text-sm font-medium">
            What is this? <span className="font-normal text-muted-foreground">(optional, recommended)</span>
          </label>
          <textarea
            id="doc-context"
            value={context}
            onChange={(e) => setContext(e.target.value)}
            disabled={status === 'uploading'}
            rows={2}
            placeholder="e.g. Our China artwork-routing process after licensor approval, updated May 2026."
            className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:opacity-50"
          />
          <p className="text-xs text-muted-foreground">
            Helps the extractor (and image reader) interpret the document. Applies to all files in this upload.
          </p>
        </div>

        {domains.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-sm font-medium">
              Likely knowledge areas{' '}
              <span className="font-normal text-muted-foreground">(optional hint — the system still classifies each claim)</span>
            </span>
            <div className="flex flex-wrap gap-1.5">
              {domains.map((d) => {
                const active = hintIds.includes(d.id);
                const belongsHere = stringList(d.belongsHere);
                const doesNotBelongHere = stringList(d.doesNotBelongHere, 2);
                const entityHints = entityHintList(d.commonEntityHints, 3);
                const tooltipId = `domain-hint-${d.id}`;
                return (
                  <span key={d.id} className="group relative inline-flex">
                    <button
                      type="button"
                      onClick={() => toggleHint(d.id)}
                      disabled={status === 'uploading'}
                      aria-describedby={tooltipId}
                      title={tooltipTitle(d)}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:opacity-50',
                        active
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input bg-background text-muted-foreground hover:text-foreground',
                      )}
                    >
                      <span>{d.name}</span>
                      <Info className="size-3 shrink-0 opacity-70" aria-hidden="true" />
                    </button>
                    <span
                      id={tooltipId}
                      role="tooltip"
                      className="pointer-events-none absolute left-0 top-full z-30 mt-1 hidden w-80 max-w-[calc(100vw-2rem)] rounded-md border bg-popover p-3 text-left text-xs text-popover-foreground opacity-0 shadow-md transition-opacity duration-150 group-hover:block group-hover:opacity-100 group-focus-within:block group-focus-within:opacity-100"
                    >
                      <span className="block font-medium text-foreground">{d.name}</span>
                      <span className="mt-1 block text-muted-foreground">{d.description}</span>
                      {belongsHere.length > 0 && (
                        <span className="mt-2 block">
                          <span className="font-medium">Use for: </span>
                          {belongsHere.join('; ')}
                        </span>
                      )}
                      {doesNotBelongHere.length > 0 && (
                        <span className="mt-1 block">
                          <span className="font-medium">Not for: </span>
                          {doesNotBelongHere.join('; ')}
                        </span>
                      )}
                      {entityHints.length > 0 && (
                        <span className="mt-1 block">
                          <span className="font-medium">Common signals: </span>
                          {entityHints.join('; ')}
                        </span>
                      )}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button type="button" size="sm" onClick={upload} disabled={files.length === 0 || status === 'uploading'}>
          {status === 'uploading'
            ? 'Uploading…'
            : `Upload${files.length ? ` ${files.length} file${files.length > 1 ? 's' : ''}` : ''}`}
        </Button>
        {status === 'done' && (
          <span className="text-xs text-green-600">
            Uploaded — ingestion runs in the background. Status updates below.
          </span>
        )}
      </div>

      {errorMsg && <p className="text-xs text-destructive">{errorMsg}</p>}
      {results.some((r) => !r.ok) && (
        <ul className="space-y-1 text-xs text-destructive">
          {results
            .filter((r): r is Extract<UploadResult, { ok: false }> => !r.ok)
            .map((r, i) => (
              <li key={i}>
                {r.fileName}: {r.error}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
