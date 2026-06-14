'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Paperclip, UploadCloud, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type UploadResult =
  | { fileName: string; ok: true; documentId: string }
  | { fileName: string; ok: false; error: string };

export function AdminDocumentUpload() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [results, setResults] = useState<UploadResult[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

      const res = await fetch('/api/admin/documents', { method: 'POST', body });
      const data = (await res.json()) as { ok: boolean; results?: UploadResult[]; error?: string };
      if (!res.ok && !data.results) {
        throw new Error(data.error ?? `Upload failed (${res.status})`);
      }
      setResults(data.results ?? []);
      setStatus(data.ok ? 'done' : 'error');
      setFiles([]);
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
