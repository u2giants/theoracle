'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

type Model = {
  id: string;
  name: string;
  contextLength: number | null;
  promptPer1M: string | null;
  completionPer1M: string | null;
};

type Status = 'idle' | 'saving' | 'saved' | 'error';

export function ModelPicker({ currentModel }: { currentModel: string | null }) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>(
    currentModel ?? 'anthropic/claude-sonnet-4.6',
  );
  const [status, setStatus] = useState<Status>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadModels() {
      try {
        const res = await fetch('/api/admin/models');
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`${res.status}: ${body}`);
        }
        const data = (await res.json()) as { models: Model[] };
        if (!cancelled) {
          setModels(data.models);
          // If the DB-stored model is in the list keep it; otherwise keep the
          // fallback so the select doesn't show a blank option.
          if (
            currentModel &&
            data.models.some((m) => m.id === currentModel)
          ) {
            setSelected(currentModel);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadModels();
    return () => {
      cancelled = true;
    };
  }, [currentModel]);

  async function save() {
    setStatus('saving');
    setSaveError(null);
    try {
      const res = await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: 'default_interview_model',
          value: selected,
          description: 'OpenRouter model used for Oracle interview chat.',
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      setStatus('saved');
      setTimeout(() => setStatus('idle'), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setStatus('error');
    }
  }

  const selectedModel = models.find((m) => m.id === selected);

  return (
    <div className="space-y-4">
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading available models…</p>
      ) : fetchError ? (
        <p className="text-sm text-destructive">
          Failed to load models: {fetchError}
        </p>
      ) : (
        <>
          <div className="space-y-2">
            <label
              htmlFor="model-select"
              className="text-sm font-medium leading-none"
            >
              Model
            </label>
            <select
              id="model-select"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setStatus('idle');
              }}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={status === 'saving'}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                  {m.promptPer1M != null
                    ? `  ·  $${m.promptPer1M} / $${m.completionPer1M} per 1M tokens`
                    : ''}
                </option>
              ))}
            </select>
          </div>

          {selectedModel && (
            <div className="rounded-md border bg-muted/30 px-4 py-3 text-xs text-muted-foreground space-y-0.5">
              <p>
                <span className="font-medium text-foreground">{selectedModel.name}</span>
              </p>
              {selectedModel.contextLength != null && (
                <p>Context: {selectedModel.contextLength.toLocaleString()} tokens</p>
              )}
              {selectedModel.promptPer1M != null && (
                <p>
                  Pricing: ${selectedModel.promptPer1M} prompt · $
                  {selectedModel.completionPer1M} completion per 1M tokens
                </p>
              )}
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button
              onClick={save}
              disabled={status === 'saving'}
              size="sm"
            >
              {status === 'saving' ? 'Saving…' : 'Save model'}
            </Button>
            {status === 'saved' && (
              <span className="text-sm text-green-600">Saved.</span>
            )}
            {status === 'error' && saveError && (
              <span className="text-sm text-destructive">{saveError}</span>
            )}
          </div>

          {currentModel && currentModel !== selected && status === 'idle' && (
            <p className="text-xs text-muted-foreground">
              Active model: <code className="font-mono">{currentModel}</code>
            </p>
          )}
        </>
      )}
    </div>
  );
}
