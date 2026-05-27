'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ModelCatalogEntry } from '@/app/api/admin/model-catalog/route';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPrice(n: number): string {
  if (n === 0) return '0';
  if (n < 0.001) return n.toFixed(5);
  if (n < 0.1) return n.toFixed(3);
  return n.toFixed(2);
}

function fmtCtx(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return n.toLocaleString();
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google (Vertex AI)',
};

const PROVIDER_ORDER = ['anthropic', 'openai', 'google'] as const;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ModelPoolEditor({ currentPool }: { currentPool: string[] }) {
  const [catalog, setCatalog] = useState<ModelCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [providerErrors, setProviderErrors] = useState<string[]>([]);
  const [pool, setPool] = useState<Set<string>>(new Set(currentPool));
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/admin/model-catalog');
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`${res.status}: ${body}`);
        }
        const data = (await res.json()) as { models: ModelCatalogEntry[]; providerErrors?: string[] };
        if (!cancelled) {
          setCatalog(data.models);
          if (data.providerErrors?.length) setProviderErrors(data.providerErrors);
        }
      } catch (err) {
        if (!cancelled) setFetchError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  function toggle(id: string) {
    setPool((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setSaveStatus('idle');
  }

  async function save() {
    setSaveStatus('saving');
    setSaveError(null);
    try {
      const res = await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: 'model_pool',
          value: Array.from(pool),
          description: 'Admin-curated shortlist of models available in the stage model pickers.',
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setSaveStatus('error');
    }
  }

  function clearPool() {
    setPool(new Set());
    setSaveStatus('idle');
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading model catalog…</p>;
  }
  if (fetchError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load catalog: {fetchError}
      </p>
    );
  }

  const filtered = filter.trim()
    ? catalog.filter(
        (m) =>
          m.id.toLowerCase().includes(filter.toLowerCase()) ||
          m.name.toLowerCase().includes(filter.toLowerCase()),
      )
    : catalog;

  return (
    <div className="space-y-5">
      {/* Provider-level errors (partial catalog) */}
      {providerErrors.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-2.5 text-sm text-amber-800 dark:text-amber-300 space-y-1">
          <p className="font-medium">Some providers could not be reached:</p>
          {providerErrors.map((e) => (
            <p key={e} className="text-xs font-mono">{e}</p>
          ))}
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Filter models…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring focus:ring-offset-2 w-64"
        />
        <span className="text-sm text-muted-foreground">
          {pool.size} model{pool.size !== 1 ? 's' : ''} selected
        </span>
        <button
          type="button"
          onClick={clearPool}
          className="text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          Clear all
        </button>
      </div>

      {/* Provider groups */}
      <div className="space-y-6">
        {PROVIDER_ORDER.map((providerKey) => {
          const providerModels = filtered.filter((m) => m.provider === providerKey);
          if (providerModels.length === 0) return null;
          return (
            <section key={providerKey}>
              <h2 className="text-sm font-semibold text-foreground mb-2">
                {PROVIDER_LABELS[providerKey]}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  ({providerModels.filter((m) => pool.has(m.id)).length} / {providerModels.length} selected)
                </span>
              </h2>
              <div className="rounded-md border divide-y">
                {providerModels.map((m) => {
                  const checked = pool.has(m.id);
                  return (
                    <label
                      key={m.id}
                      className={cn(
                        'flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors',
                        checked && 'bg-muted/20',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(m.id)}
                        className="size-4 rounded border-gray-300 accent-primary"
                      />
                      <div className="flex-1 min-w-0">
                        <span className="font-mono text-xs text-foreground truncate block">{m.id}</span>
                        {m.name !== m.id && (
                          <span className="text-xs text-muted-foreground truncate block">{m.name}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 shrink-0 text-xs text-muted-foreground">
                        {m.contextLength != null && (
                          <span>{fmtCtx(m.contextLength)} ctx</span>
                        )}
                        {m.promptPer1M != null && (
                          <span className="font-mono">
                            {m.promptPer1M === 0 && (m.completionPer1M ?? 0) === 0
                              ? 'Free'
                              : `$${fmtPrice(m.promptPer1M)}/$${fmtPrice(m.completionPer1M ?? 0)}`}
                          </span>
                        )}
                        {m.vision && (
                          <span className="rounded bg-muted px-1 py-0.5 text-[10px]">vision</span>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>

      {/* Save bar */}
      <div className="flex items-center gap-3 pt-2 border-t">
        <Button onClick={save} disabled={saveStatus === 'saving'} size="sm">
          {saveStatus === 'saving' ? 'Saving…' : 'Save pool'}
        </Button>
        {saveStatus === 'saved' && (
          <span className="text-sm text-green-600">Pool saved. Return to Settings to pick from this list.</span>
        )}
        {saveStatus === 'error' && saveError && (
          <span className="text-sm text-destructive">{saveError}</span>
        )}
      </div>
    </div>
  );
}
