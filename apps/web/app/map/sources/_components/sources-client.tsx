'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { FileText, RefreshCw, Trash2, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

type SourceRow = {
  id: string;
  kind: string;
  title: string;
  original_filename: string | null;
  bytes: number;
  department_hint: string | null;
  effective_date: string | null;
  read_state: 'queued' | 'read' | 'failed';
  read_error: string | null;
  created_at: string | null;
};

type LogLine = { text: string; ok: boolean };

const READ_STATE_STYLES: Record<SourceRow['read_state'], string> = {
  queued: 'bg-amber-100 text-amber-900',
  read: 'bg-emerald-100 text-emerald-900',
  failed: 'bg-red-100 text-red-900',
};

function formatBytes(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

export function SourcesClient({ isAdmin }: { isAdmin: boolean }) {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState<'idle' | 'upload' | 'transcript' | 'delete'>('idle');
  const [log, setLog] = useState<LogLine[]>([]);
  const [transcriptTitle, setTranscriptTitle] = useState('');
  const [transcriptText, setTranscriptText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchSources = useCallback(async (): Promise<{
    rows: SourceRow[];
    error: string | null;
  }> => {
    try {
      const response = await fetch('/api/brain/sources');
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error ?? `load failed (${response.status})`);
      }
      const body = await response.json();
      return { rows: body.sources ?? [], error: null };
    } catch (err) {
      return {
        rows: [],
        error: err instanceof Error ? err.message : 'load failed',
      };
    }
  }, []);

  const refresh = useCallback(async () => {
    const result = await fetchSources();
    setSources(result.rows);
    setLoadError(result.error);
    setLoaded(true);
  }, [fetchSources]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const result = await fetchSources();
      if (cancelled) return;
      setSources(result.rows);
      setLoadError(result.error);
      setLoaded(true);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [fetchSources]);

  function addFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
    setLog([]);
  }

  function appendLog(text: string, ok: boolean) {
    setLog((prev) => [...prev, { text, ok }]);
  }

  async function uploadFiles() {
    if (files.length === 0) return;
    setBusy('upload');
    setLog([]);
    for (const file of files) {
      const form = new FormData();
      form.append('file', file, file.name);
      try {
        const response = await fetch('/api/brain/sources', {
          method: 'POST',
          body: form,
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          appendLog(
            `${file.name}: ${body.detail ?? body.error ?? `upload failed (${response.status})`}`,
            false,
          );
          continue;
        }
        appendLog(
          body.duplicate
            ? `${file.name}: duplicate of an existing source`
            : `${file.name}: queued for reading`,
          true,
        );
      } catch {
        appendLog(`${file.name}: upload failed`, false);
      }
    }
    setFiles([]);
    setBusy('idle');
    await refresh();
  }

  async function submitTranscript() {
    if (!transcriptText.trim()) return;
    setBusy('transcript');
    setLog([]);
    try {
      const response = await fetch('/api/brain/sources/transcript', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          text: transcriptText,
          title: transcriptTitle.trim() || undefined,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        appendLog(
          body.detail ?? body.error ?? `transcript failed (${response.status})`,
          false,
        );
      } else {
        appendLog(
          body.duplicate
            ? 'Transcript duplicate of an existing source'
            : 'Transcript queued for reading',
          true,
        );
        setTranscriptText('');
        setTranscriptTitle('');
      }
    } catch {
      appendLog('Transcript failed to send', false);
    }
    setBusy('idle');
    await refresh();
  }

  async function removeSource(id: string, title: string) {
    setBusy('delete');
    try {
      const response = await fetch(`/api/brain/sources/${id}`, { method: 'DELETE' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        appendLog(body.detail ?? body.error ?? `delete failed (${response.status})`, false);
      } else {
        appendLog(`${title}: deleted`, true);
      }
    } catch {
      appendLog(`${title}: delete failed`, false);
    }
    setBusy('idle');
    await refresh();
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Upload documents and diagrams</CardTitle>
          <CardDescription>
            PDF, DOCX, XLSX, PPTX, Markdown/Text and PNG/JPG/SVG files. Drag
            them in or choose files, then upload.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            className={cn(
              'flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-sm text-muted-foreground',
              dragOver ? 'border-primary bg-primary/5' : 'border-border',
            )}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragOver(false);
              addFiles(event.dataTransfer.files);
            }}
          >
            <UploadCloud className="h-6 w-6" />
            <span>Drop files here, or click to choose</span>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => addFiles(event.target.files)}
            />
          </div>
          {files.length > 0 && (
            <ul className="space-y-1 text-sm">
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`} className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <span className="flex-1 truncate">{file.name}</span>
                  <span className="text-muted-foreground">{formatBytes(file.size)}</span>
                </li>
              ))}
            </ul>
          )}
          <Button onClick={uploadFiles} disabled={files.length === 0 || busy !== 'idle'}>
            {busy === 'upload' ? 'Uploading…' : `Upload ${files.length || ''} file(s)`}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Add a transcript</CardTitle>
          <CardDescription>
            Paste VTT, a Teams or Recall JSON export, or plain
            &quot;Speaker: text&quot; lines.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            placeholder="Title (optional)"
            value={transcriptTitle}
            onChange={(event) => setTranscriptTitle(event.target.value)}
          />
          <textarea
            className="min-h-40 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            placeholder={'Ilona: Morning Marco, did the spring program POs go out yet?\nMarco: Not yet…'}
            value={transcriptText}
            onChange={(event) => setTranscriptText(event.target.value)}
          />
          <Button
            onClick={submitTranscript}
            disabled={transcriptText.trim().length === 0 || busy !== 'idle'}
          >
            {busy === 'transcript' ? 'Sending…' : 'Add transcript'}
          </Button>
        </CardContent>
      </Card>

      {log.length > 0 && (
        <Card>
          <CardContent className="space-y-1 pt-6 text-sm">
            {log.map((line, index) => (
              <p key={index} className={line.ok ? 'text-emerald-700' : 'text-red-700'}>
                {line.text}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Sources</CardTitle>
            <CardDescription>
              {loaded ? `${sources.length} source(s) in the map queue` : 'Loading…'}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {loadError && <p className="text-sm text-red-700">{loadError}</p>}
          {!loadError && loaded && sources.length === 0 && (
            <p className="text-sm text-muted-foreground">No sources yet.</p>
          )}
          {sources.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Title</th>
                    <th className="py-2 pr-3 font-medium">Kind</th>
                    <th className="py-2 pr-3 font-medium">Read state</th>
                    <th className="py-2 pr-3 font-medium">Department</th>
                    <th className="py-2 pr-3 font-medium">Size</th>
                    <th className="py-2 pr-3 font-medium">Added</th>
                    {isAdmin && <th className="py-2 font-medium" />}
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <tr key={source.id} className="border-b last:border-0">
                      <td className="py-2 pr-3">
                        <div className="font-medium">{source.title}</div>
                        {source.read_error && (
                          <div className="text-xs text-red-700">{source.read_error}</div>
                        )}
                      </td>
                      <td className="py-2 pr-3 capitalize">{source.kind}</td>
                      <td className="py-2 pr-3">
                        <span
                          className={cn(
                            'rounded-full px-2 py-0.5 text-xs font-medium',
                            READ_STATE_STYLES[source.read_state],
                          )}
                        >
                          {source.read_state}
                        </span>
                      </td>
                      <td className="py-2 pr-3">{source.department_hint ?? '—'}</td>
                      <td className="py-2 pr-3">{formatBytes(source.bytes)}</td>
                      <td className="py-2 pr-3">
                        {source.created_at ? source.created_at.slice(0, 10) : '—'}
                      </td>
                      {isAdmin && (
                        <td className="py-2 text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy !== 'idle'}
                            onClick={() => removeSource(source.id, source.title)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
