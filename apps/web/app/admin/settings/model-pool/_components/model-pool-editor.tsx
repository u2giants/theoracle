'use client';

import { useEffect, useState } from 'react';
import { Braces, Eye, FileText, Sparkles, Wrench, Zap } from 'lucide-react';
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

// ---------------------------------------------------------------------------
// Capability badge
// ---------------------------------------------------------------------------

type IconComponent = React.ComponentType<{ className?: string }>;

function CapBadge({ icon: Icon, label, cls }: { icon: IconComponent; label: string; cls: string }) {
  return (
    <span className={cn('inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium', cls)}>
      <Icon className="h-2.5 w-2.5 shrink-0" />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------

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

// Minimum capability a model must have to be selectable for each stage.
// Interview and Synthesis use tool_call structured-output strategy → need tools.
// Extraction uses native_json_schema → needs structuredOutputs.
const STAGE_CAP_REQUIREMENT: Record<Stage, { field: keyof ModelCatalogEntry; label: string }> = {
  interview: { field: 'tools', label: 'tool calling' },
  extraction: { field: 'structuredOutputs', label: 'structured outputs' },
  synthesis: { field: 'tools', label: 'tool calling' },
};

/** True when we have enrichment data for this model (context OR pricing populated). */
function hasEnrichment(m: ModelCatalogEntry): boolean {
  return m.contextLength != null || m.promptPer1M != null;
}

/** False only when enrichment is present AND the required cap is explicitly false. */
function meetsStageReq(m: ModelCatalogEntry, stage: Stage): boolean {
  if (!hasEnrichment(m)) return true; // unknown — allow
  return !!m[STAGE_CAP_REQUIREMENT[stage].field];
}

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
  const [refreshErrors, setRefreshErrors] = useState<string[]>([]);
  const [refreshUnenriched, setRefreshUnenriched] = useState<string[]>([]);
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
    setRefreshErrors([]);
    try {
      const res = await fetch('/api/admin/model-catalog', { method: 'POST' });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      const data = (await res.json()) as { models: ModelCatalogEntry[]; refreshedAt: string; errors?: string[]; unenrichedIds?: string[] };
      setCatalog(data.models);
      setRefreshedAt(data.refreshedAt);
      setRefreshErrors(data.errors ?? []);
      setRefreshUnenriched(data.unenrichedIds ?? []);
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
          current list from the Anthropic, OpenAI, and Google APIs (with pricing
          and capability metadata from OpenRouter).
        </p>
        <Button onClick={refreshCatalog} disabled={refreshing} size="sm">
          {refreshing ? 'Refreshing…' : 'Refresh catalog'}
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
            {refreshedAt ? new Date(refreshedAt).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'never'}
          </strong>
          {' '}({catalog.length} models)
        </span>
        <Button onClick={refreshCatalog} disabled={refreshing} size="sm" variant="outline">
          {refreshing ? 'Refreshing…' : 'Refresh catalog'}
        </Button>
        {refreshError && <span className="text-sm text-destructive">{refreshError}</span>}
      </div>
      {refreshErrors.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 space-y-0.5 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
          <p className="font-medium">Partial refresh — some sources failed:</p>
          {refreshErrors.map((e, i) => <p key={i}>• {e}</p>)}
        </div>
      )}
      {refreshUnenriched.length > 0 && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none">
            {catalog.length - refreshUnenriched.length}/{catalog.length} models enriched from OpenRouter —{' '}
            <span className="text-amber-600 dark:text-amber-400">{refreshUnenriched.length} without pricing/capability data</span>
            {' '}(click to see)
          </summary>
          <ul className="mt-1.5 ml-3 space-y-0.5 font-mono">
            {refreshUnenriched.map((id) => <li key={id}>{id}</li>)}
          </ul>
        </details>
      )}

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
                          <div className="flex flex-wrap items-center gap-1 mt-1">
                            {m.vision && <CapBadge icon={Eye} label="vision" cls="bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300" />}
                            {m.thinking && <CapBadge icon={Sparkles} label="thinking" cls="bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300" />}
                            {m.tools && <CapBadge icon={Wrench} label="tools" cls="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" />}
                            {m.structuredOutputs && <CapBadge icon={Braces} label="structured" cls="bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300" />}
                            {m.promptCaching && <CapBadge icon={Zap} label="caching" cls="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" />}
                            {m.pdf && <CapBadge icon={FileText} label="pdf" cls="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400" />}
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
                          const eligible = meetsStageReq(m, stage);
                          const req = STAGE_CAP_REQUIREMENT[stage];
                          return (
                            <td key={stage} className="px-3 py-2 text-center align-top">
                              <label
                                title={eligible ? undefined : `Requires ${req.label}`}
                                className={cn(
                                  'inline-flex items-center justify-center rounded px-1.5 py-0.5',
                                  eligible ? 'cursor-pointer' : 'cursor-not-allowed opacity-35',
                                  checked && eligible && 'bg-primary/10',
                                )}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  disabled={!eligible}
                                  onChange={() => eligible && toggle(stage, m.id)}
                                  className="size-4 rounded border-gray-300 accent-primary disabled:cursor-not-allowed"
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
