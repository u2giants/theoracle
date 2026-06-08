'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CheckCircle2, Loader2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

interface ImportChannelOption {
  id: string;
  name: string;
  messageCount: number;
}

interface ImportResult {
  importId: string;
  channelId: string;
  messageCount: number;
}

export function AdminImportForm({ channels }: { channels: ImportChannelOption[] }) {
  const [title, setTitle] = useState('');
  const [sourceLabel, setSourceLabel] = useState('');
  const [channelId, setChannelId] = useState('');
  const [content, setContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const characterCount = content.trim().length;
  const canSubmit = title.trim().length > 0 && characterCount >= 20 && !isSubmitting;
  const estimatedMessages = useMemo(
    () => Math.max(1, Math.ceil(characterCount / 9000)),
    [characterCount],
  );

  async function submit() {
    if (!canSubmit) return;
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    const res = await fetch('/api/admin/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        sourceLabel: sourceLabel || undefined,
        content,
        channelId: channelId || undefined,
      }),
    });

    const payload = await res.json().catch(() => null);
    setIsSubmitting(false);

    if (!res.ok) {
      setError(payload?.error ?? 'Import failed.');
      return;
    }

    setResult(payload as ImportResult);
    setContent('');
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Raw information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Title</span>
            <Input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={120}
              placeholder="Design file naming and server storage notes"
            />
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Source label</span>
            <Input
              value={sourceLabel}
              onChange={(event) => setSourceLabel(event.target.value)}
              maxLength={200}
              placeholder="Albert notes, SOP draft, Teams recap..."
            />
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Destination</span>
            <select
              value={channelId}
              onChange={(event) => setChannelId(event.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="">Create a new import channel</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channel.name} ({channel.messageCount})
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Content</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              maxLength={100000}
              rows={18}
              className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm leading-6 ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              placeholder="Paste raw operational information here. Keep source wording intact when possible."
            />
          </label>

          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>{characterCount.toLocaleString()} / 100,000 characters</span>
            <span>Will create about {estimatedMessages} pending message{estimatedMessages === 1 ? '' : 's'}</span>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {result && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4" aria-hidden />
              <span>{result.messageCount} message{result.messageCount === 1 ? '' : 's'} queued.</span>
              <Link href={`/admin/messages?channel=${result.channelId}`} className="font-medium underline underline-offset-4">
                View transcript
              </Link>
            </div>
          )}

          <Button type="button" onClick={submit} disabled={!canSubmit}>
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Upload className="h-4 w-4" aria-hidden />
            )}
            Queue import
          </Button>
        </CardContent>
      </Card>

      <aside className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Pipeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <div className="rounded-md border px-3 py-2">
              Raw text becomes pending user messages.
            </div>
            <div className="rounded-md border px-3 py-2">
              Extraction chooses candidate domains from active taxonomy.
            </div>
            <div className="rounded-md border px-3 py-2">
              Quote, taxonomy, and sensitivity validators gate promotion.
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
