'use client';

import { useEffect, useState } from 'react';
import { Paperclip, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type UploadedMessage = {
  id: string;
  channelId: string;
  employeeId: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
  authorName: string | null;
};

export function DocumentUpload({
  channelId,
  employeeId: _employeeId,
  initialFile,
  onDone,
}: {
  channelId: string;
  employeeId: string;
  /** Pre-populate the file (e.g. from a drag-and-drop). */
  initialFile?: File | null;
  onDone: (message: UploadedMessage | null) => void;
}) {
  const [file, setFile] = useState<File | null>(initialFile ?? null);
  const [caption, setCaption] = useState('');
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Sync when a file is dropped externally (drag-to-upload from parent).
  useEffect(() => {
    if (initialFile) {
      const id = window.setTimeout(() => {
        setFile(initialFile);
        setStatus('idle');
        setErrorMsg(null);
      }, 0);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [initialFile]);

  async function upload() {
    if (!file) return;
    setStatus('uploading');
    setErrorMsg(null);

    try {
      const body = new FormData();
      body.append('file', file);
      body.append('channelId', channelId);
      if (caption.trim()) body.append('caption', caption.trim());

      const res = await fetch('/api/documents', {
        method: 'POST',
        body,
        // Do NOT set Content-Type — browser adds the multipart boundary.
      });

      if (!res.ok) {
        const errBody = await res.text();
        console.error('[upload] /api/documents failed', res.status, errBody);
        throw new Error(`Upload failed (${res.status}): ${errBody}`);
      }

      const data = (await res.json()) as {
        ok: boolean;
        documentId: string;
        storagePath: string;
        message: UploadedMessage | null;
      };

      setStatus('done');
      onDone(data.message);
    } catch (err) {
      console.error('[upload] failed', err);
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : 'Upload failed.');
    }
  }

  function clearFile() {
    setFile(null);
    setCaption('');
    setStatus('idle');
    setErrorMsg(null);
  }

  return (
    <div className="space-y-2">
      {/* File picker row */}
      <div className="flex items-center gap-2">
        {file ? (
          <div className="flex flex-1 items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
            <Paperclip className="size-4 shrink-0 text-muted-foreground" />
            <span className="flex-1 truncate text-foreground">{file.name}</span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {(file.size / 1024).toFixed(0)} KB
            </span>
            <button
              type="button"
              onClick={clearFile}
              className="shrink-0 text-muted-foreground hover:text-foreground"
              aria-label="Remove file"
            >
              <X className="size-4" />
            </button>
          </div>
        ) : (
          <label className="flex-1 cursor-pointer">
            <div className="flex items-center gap-2 rounded-md border border-dashed bg-background px-3 py-2 text-sm text-muted-foreground hover:border-ring hover:text-foreground">
              <Paperclip className="size-4 shrink-0" />
              <span>Choose a file…</span>
            </div>
            <input
              type="file"
              className="sr-only"
              disabled={status === 'uploading'}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setFile(f);
                setStatus('idle');
                setErrorMsg(null);
                // Reset input so the same file can be reselected after clear.
                e.target.value = '';
              }}
            />
          </label>
        )}

        <Button
          type="button"
          size="sm"
          onClick={upload}
          disabled={!file || status === 'uploading'}
        >
          {status === 'uploading' ? 'Sending…' : 'Send'}
        </Button>
      </div>

      {/* Caption / question */}
      {file && (
        <Input
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="Add a message or question about this file… (optional)"
          disabled={status === 'uploading'}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && file && status !== 'uploading') {
              e.preventDefault();
              void upload();
            }
          }}
        />
      )}

      {file && file.type.startsWith('image/') && status === 'idle' && (
        <p className="text-xs text-amber-600">
          Tip: add a caption so Oracle knows what to look for in this image.
          If Oracle says it can&apos;t see the image, use the main text box to
          describe it after uploading.
        </p>
      )}
      {status === 'done' && (
        <p className="text-xs text-green-600">Sent.</p>
      )}
      {errorMsg && (
        <p className="text-xs text-destructive">{errorMsg}</p>
      )}
    </div>
  );
}
