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

const STAGES = ['interview', 'extraction', 'synthesis'] as const;
type Stage = (typeof STAGES)[number];

const STAGE_LABELS: Record<Stage, string> = {
  interview: 'Interview',
  extraction: 'Extraction',
  synthesis: 'Synthesis',
};

const STAGE_SETTING_KEYS: Record<Stage, string> = {
  interview: 'model_pool_interview',
  extraction: 'model_pool_extraction',
  synthesis: 'model_pool_synthesis',
};

type PoolState = Record<Stage, Set<string>>;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ModelPoolEditor({
  initial,
}: {
  initial: Record<Stage, string[]>;
}) {
  const [catalog, setCatalog] = useState<ModelCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [pools, setPools] = useState<PoolState>({
    interview: new Set(initial.interview),
    extraction: new Set(initial.extraction),
    synthesis: new Set(initial.synthesis),
  });
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
        const data = (await res.json()) as { models: ModelCatalogEntry[]; refreshedAt: string | null };
        if (!cancelled) {
          setCatalog(data.models);
          setRefreshedAt(data.refreshedAt);
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

  async function refreshCatalog() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const res = await fetch('/api/admin/model-catalog', { method: 'POST' });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      const data = (await res.json()) as { models: ModelCatalogEntry[]; refreshedAt: string };
      setCatalog(data.models);
      setRefreshedAt(data.refreshedAt);
    } catch (err) {
      setRefreshError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }

  function toggle(stage: Stage, id: string) {
    setPools((prev) => {
      const next = { ...prev, [stage]: new Set(prev[stage]) };
      if (next[stage].has(id)) next[stage].delete(id);
      else next[stage].add(id);
      return next;
    });
    setSaveStatus('idle');
  }

  function clearStage(stage: Stage) {
    setPools((prev) => ({ ...prev, [stage]: new Set<string>() }));
    setSaveStatus('idle');
  }

  function copyFrom(source: Stage, target: Stage) {
    setPools((prev) => ({ ...prev, [target]: new Set(prev[source]) }));
    setSaveStatus('idle');
  }

  async function save() {
    setSaveStatus('saving');
    setSaveError(null);
    try {
      // Save all three pools sequentially so a failure on one is reported clearly.
      for (const stage of STAGES) {
        const res = await fetch('/api/admin/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            key: STAGE_SETTING_KEYS[stage],
            value: Array.from(pools[stage]),
            description: `Admin-curated model shortlist for the ${STAGE_LABELS[stage]} stage picker.`,
          }),
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`${STAGE_LABELS[stage]}: ${res.status}: ${body}`);
        }
      }
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setSaveStatus('error');
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading model catalog…</p>;
  }
  if (fetchError) {
    return (
      <p className="text-sm text-destructive">Failed to load catalog: {fetchError}</p>
    );
  }
  if (catalog.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          The model catalog hasn&apos;t been refreshed yet. Click below to pull the
          current list from openrouter.ai (covers Anthropic, OpenAI, and Google
          Vertex models with pricing).
        </p>
        <Button onClick={refreshCatalog} disabled={refreshing} size="sm">
          {refreshing ? 'Refreshing…' : 'Refresh catalog from OpenRouter'}
        </Button>
        {refreshError && <p className="text-sm text-destructive">{refreshError}</p>}
      </div>
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
      {/* Catalog freshness + refresh */}
      <div className="flex items-center gap-3 flex-wrap text-sm">
        <span className="text-muted-foreground">
          Catalog last refreshed:{' '}
          <strong className="text-foreground">
            {refreshedAt ? new Date(refreshedAt).toLocaleString('en-US', { timeZone: 'America/New_York', dateStyle: 'medium', timeStyle: 'short', timeZoneName: 'short' }) : 'never'}
          </strong>
          {' '}({catalog.length} models)
        </span>
        <Button onClick={refreshCatalog} disabled={refreshing} size="sm" variant="outline">
          {refreshing ? 'Refreshing…' : 'Refresh from OpenRouter'}
        </Button>
        {refreshError && <span className="text-sm text-destructive">{refreshError}</span>}
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Filter models…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring focus:ring-offset-2 w-64"
        />
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {STAGES.map((s) => (
            <span key={s} className="rounded bg-muted px-2 py-0.5">
              {STAGE_LABELS[s]}: <strong className="text-foreground">{pools[s].size}</strong>
            </span>
          ))}
        </div>
      </div>

      {/* Per-stage controls row */}
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground">
        {STAGES.map((stage) => (
          <div key={stage} className="flex items-center gap-2">
            <span className="font-medium text-foreground">{STAGE_LABELS[stage]}:</span>
            <button
              type="button"
              onClick={() => clearStage(stage)}
              className="underline underline-offset-2 hover:text-foreground"
            >
              Clear
            </button>
            {STAGES.filter((s) => s !== stage).map((src) => (
              <button
                key={src}
                type="button"
                onClick={() => copyFrom(src, stage)}
                className="underline underline-offset-2 hover:text-foreground"
                title={`Replace ${STAGE_LABELS[stage]} pool with a copy of ${STAGE_LABELS[src]}`}
              >
                Copy from {STAGE_LABELS[src]}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Provider groups, with stage-column checkboxes per row */}
      <div className="space-y-6">
        {PROVIDER_ORDER.map((providerKey) => {
          const providerModels = filtered.filter((m) => m.provider === providerKey);
          if (providerModels.length === 0) return null;
          return (
            <section key={providerKey}>
              <h2 className="text-sm font-semibold text-foreground mb-2">
                {PROVIDER_LABELS[providerKey]}
              </h2>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40">
                    <tr>
                      <th className="text-left px-4 py-2 font-medium text-xs text-muted-foreground">Model</th>
                      <th className="text-right px-3 py-2 font-medium text-xs text-muted-foreground whitespace-nowrap">Context</th>
                      <th className="text-right px-3 py-2 font-medium text-xs text-muted-foreground whitespace-nowrap">$/1M (in/out)</th>
                      {STAGES.map((stage) => (
                        <th key={stage} className="text-center px-3 py-2 font-medium text-xs text-muted-foreground whitespace-nowrap">
                          {STAGE_LABELS[stage]}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {providerModels.map((m) => (
                      <tr key={m.id} className="hover:bg-muted/30">
                        <td className="px-4 py-2 align-top">
                          <span className="font-mono text-xs text-foreground block">{m.id}</span>
                          {m.name !== m.id && (
                            <span className="text-xs text-muted-foreground block mt-0.5">{m.name}</span>
                          )}
                          <div className="flex items-center gap-1.5 mt-1">
                            {m.vision && (
                              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">vision</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 align-top text-right text-xs text-muted-foreground whitespace-nowrap">
                          {m.contextLength != null ? `${fmtCtx(m.contextLength)} tok` : '—'}
                        </td>
                        <td className="px-3 py-2 align-top text-right text-xs text-muted-foreground font-mono whitespace-nowrap">
                          {m.promptPer1M != null
                            ? (m.promptPer1M === 0 && (m.completionPer1M ?? 0) === 0
                              ? 'Free'
                              : `$${fmtPrice(m.promptPer1M)} / $${fmtPrice(m.completionPer1M ?? 0)}`)
                            : '—'}
                        </td>
                        {STAGES.map((stage) => {
                          const checked = pools[stage].has(m.id);
                          return (
                            <td key={stage} className="px-3 py-2 text-center align-top">
                              <label
                                className={cn(
                                  'inline-flex items-center justify-center cursor-pointer rounded px-1.5 py-0.5',
                                  checked && 'bg-primary/10',
                                )}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => toggle(stage, m.id)}
                                  className="size-4 rounded border-gray-300 accent-primary"
                                  aria-label={`Include ${m.id} in ${STAGE_LABELS[stage]} pool`}
                                />
                              </label>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>

      {/* Save bar */}
      <div className="flex items-center gap-3 pt-2 border-t">
        <Button onClick={save} disabled={saveStatus === 'saving'} size="sm">
          {saveStatus === 'saving' ? 'Saving all pools…' : 'Save all pools'}
        </Button>
        {saveStatus === 'saved' && (
          <span className="text-sm text-green-600">All three pools saved.</span>
        )}
        {saveStatus === 'error' && saveError && (
          <span className="text-sm text-destructive">{saveError}</span>
        )}
      </div>
    </div>
  );
}
