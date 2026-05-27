'use client';

import { useEffect, useState } from 'react';
import {
  Braces,
  ChevronDown,
  ChevronUp,
  ChevronsUpDown,
  Eye,
  FileText,
  Maximize2,
  Sparkles,
  Type,
  Wrench,
  Zap,
} from 'lucide-react';
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

type IconComponent = React.ComponentType<{ className?: string }>;

// ---------------------------------------------------------------------------
// Capability metadata
// ---------------------------------------------------------------------------

type CapabilityField = 'vision' | 'thinking' | 'tools' | 'structuredOutputs' | 'promptCaching' | 'pdf' | 'outputCap';

interface CapabilityMeta {
  field: CapabilityField;
  short: string;
  long: string;
  icon: IconComponent;
  color: string;
}

const CAPABILITIES: ReadonlyArray<CapabilityMeta> = [
  { field: 'vision',            short: 'Vision',     long: 'Vision (image input)',                   icon: Eye,      color: 'text-sky-600 dark:text-sky-400' },
  { field: 'thinking',          short: 'Reasoning',  long: 'Reasoning / include_reasoning',          icon: Sparkles, color: 'text-violet-600 dark:text-violet-400' },
  { field: 'tools',             short: 'Tools',      long: 'Tools / tool_choice',                    icon: Wrench,   color: 'text-emerald-600 dark:text-emerald-400' },
  { field: 'structuredOutputs', short: 'Structured', long: 'Structured outputs / response_format',   icon: Braces,   color: 'text-orange-600 dark:text-orange-400' },
  { field: 'promptCaching',     short: 'Caching',    long: 'Prompt caching',                         icon: Zap,      color: 'text-amber-600 dark:text-amber-400' },
  { field: 'outputCap',         short: 'OutCap',     long: 'Output cap (max_completion_tokens or max_tokens)', icon: Type, color: 'text-teal-600 dark:text-teal-400' },
  { field: 'pdf',               short: 'PDF',        long: 'PDF input',                              icon: FileText, color: 'text-slate-600 dark:text-slate-400' },
];

const CAP_BY_FIELD = Object.fromEntries(CAPABILITIES.map((c) => [c.field, c])) as Record<CapabilityField, CapabilityMeta>;

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google (Vertex AI)',
  deepseek: 'DeepSeek',
  qwen: 'Alibaba Qwen',
};

const PROVIDER_ORDER = ['anthropic', 'openai', 'google', 'deepseek', 'qwen'] as const;

const STAGES = ['interview', 'extraction', 'synthesis'] as const;
type Stage = (typeof STAGES)[number];

const STAGE_LABELS: Record<Stage, string> = {
  interview: 'Interview',
  extraction: 'Extraction',
  synthesis: 'Synthesis',
};

// ---------------------------------------------------------------------------
// Stage requirements — model must satisfy ALL listed predicates to be eligible.
//
// Spec (per session 2026-05-27):
//   Interview:  tools, structured, vision, context > 100K
//   Extraction: structured, reasoning (thinking), vision, context > 100K
//   Synthesis:  context > 400K, structured (response_format), output cap
// ---------------------------------------------------------------------------

interface StageRequirement {
  /** Predicate against the model entry. */
  check: (m: ModelCatalogEntry) => boolean;
  /** Header label / tooltip text. */
  label: string;
  /** Icon shown in the stage's column header. */
  icon: IconComponent;
  /** Tailwind text-color class for the icon. */
  color: string;
}

const CTX_REQ = (threshold: number): StageRequirement => ({
  check: (m) => m.contextLength != null && m.contextLength > threshold,
  label: `Context > ${threshold >= 1_000_000 ? `${threshold / 1_000_000}M` : `${threshold / 1_000}K`}`,
  icon: Maximize2,
  color: 'text-indigo-600 dark:text-indigo-400',
});

const CAP_REQ = (field: CapabilityField): StageRequirement => {
  const meta = CAP_BY_FIELD[field];
  return {
    check: (m) => !!m[field],
    label: meta.long,
    icon: meta.icon,
    color: meta.color,
  };
};

const STAGE_REQUIREMENTS: Record<Stage, StageRequirement[]> = {
  interview: [
    CAP_REQ('tools'),
    CAP_REQ('structuredOutputs'),
    CAP_REQ('vision'),
    CTX_REQ(100_000),
  ],
  extraction: [
    CAP_REQ('structuredOutputs'),
    CAP_REQ('thinking'),
    CAP_REQ('vision'),
    CTX_REQ(100_000),
  ],
  synthesis: [
    CTX_REQ(400_000),
    CAP_REQ('structuredOutputs'),
    CAP_REQ('outputCap'),
  ],
};

/** True when we have enrichment data for this model (context OR pricing populated). */
function hasEnrichment(m: ModelCatalogEntry): boolean {
  return m.contextLength != null || m.promptPer1M != null;
}

/** Returns the missing requirements for a stage, or [] if eligible (or unknown). */
function missingReqs(m: ModelCatalogEntry, stage: Stage): StageRequirement[] {
  if (!hasEnrichment(m)) return []; // unknown — allow
  return STAGE_REQUIREMENTS[stage].filter((r) => !r.check(m));
}

const STAGE_SETTING_KEYS: Record<Stage, string> = {
  interview: 'model_pool_interview',
  extraction: 'model_pool_extraction',
  synthesis: 'model_pool_synthesis',
};

type PoolState = Record<Stage, Set<string>>;
type SortKey = 'context' | 'price' | null;
type SortDir = 'asc' | 'desc';

// ---------------------------------------------------------------------------
// Header components
// ---------------------------------------------------------------------------

function SortLabel({ label, active, dir, onClick }: {
  label: string; active: boolean; dir: SortDir; onClick: () => void;
}) {
  const Icon = !active ? ChevronsUpDown : dir === 'asc' ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
    >
      {label}
      <Icon className={cn('h-3 w-3', active ? 'text-foreground' : 'opacity-40')} />
    </button>
  );
}

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
  const [refreshUnenrichedCount, setRefreshUnenrichedCount] = useState(0);
  const [pools, setPools] = useState<PoolState>({
    interview: new Set(initial.interview),
    extraction: new Set(initial.extraction),
    synthesis: new Set(initial.synthesis),
  });
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);

  // In-header filter state
  const [nameFilter, setNameFilter] = useState('');
  const [minContext, setMinContext] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [capFilters, setCapFilters] = useState<Set<CapabilityField>>(new Set());
  const [sortBy, setSortBy] = useState<SortKey>(null);
  const [sortDir, setSortDir] = useState<SortDir>('desc');

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
      setRefreshUnenrichedCount((data.unenrichedIds ?? []).length);
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

  function toggleSort(key: 'context' | 'price') {
    if (sortBy === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortBy(key); setSortDir('desc'); }
  }

  function toggleCapFilter(field: CapabilityField) {
    setCapFilters((prev) => {
      const next = new Set(prev);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });
  }

  function resetAllFilters() {
    setNameFilter(''); setMinContext(''); setMaxPrice('');
    setCapFilters(new Set()); setSortBy(null);
  }

  async function save() {
    setSaveStatus('saving');
    setSaveError(null);
    try {
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
    return <p className="text-sm text-destructive">Failed to load catalog: {fetchError}</p>;
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

  // ── Hide unenriched models from the table ────────────────────────────────
  const enrichedCatalog = catalog.filter(hasEnrichment);
  const hiddenCount = catalog.length - enrichedCatalog.length;

  // ── Apply filters ────────────────────────────────────────────────────────
  const minCtxNum = minContext.trim() ? parseInt(minContext.replace(/[^\d]/g, ''), 10) || null : null;
  const maxPriceNum = maxPrice.trim() ? parseFloat(maxPrice) : null;
  const filterText = nameFilter.trim().toLowerCase();

  const filtered = enrichedCatalog.filter((m) => {
    if (filterText && !m.id.toLowerCase().includes(filterText) && !m.name.toLowerCase().includes(filterText)) return false;
    if (minCtxNum != null && (m.contextLength == null || m.contextLength < minCtxNum)) return false;
    if (maxPriceNum != null && Number.isFinite(maxPriceNum) && (m.promptPer1M == null || m.promptPer1M > maxPriceNum)) return false;
    for (const cap of capFilters) {
      if (!m[cap]) return false;
    }
    return true;
  });

  // ── Sort within provider groups ──────────────────────────────────────────
  function sortModels(models: ModelCatalogEntry[]): ModelCatalogEntry[] {
    if (sortBy == null) return models;
    return [...models].sort((a, b) => {
      const aN = sortBy === 'context' ? a.contextLength : a.promptPer1M;
      const bN = sortBy === 'context' ? b.contextLength : b.promptPer1M;
      if (aN == null && bN == null) return 0;
      if (aN == null) return 1;
      if (bN == null) return -1;
      return sortDir === 'asc' ? aN - bN : bN - aN;
    });
  }

  const filtersActive = !!(nameFilter || minContext || maxPrice || capFilters.size || sortBy);

  return (
    <div className="space-y-5">
      {/* Catalog freshness + refresh */}
      <div className="flex items-center gap-3 flex-wrap text-sm">
        <span className="text-muted-foreground">
          Catalog last refreshed:{' '}
          <strong className="text-foreground">
            {refreshedAt ? new Date(refreshedAt).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'never'}
          </strong>
          {' '}({enrichedCatalog.length} models shown
          {hiddenCount > 0 && (
            <span className="text-muted-foreground/70">, {hiddenCount} hidden (no enrichment)</span>
          )}
          )
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
      {refreshUnenrichedCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {refreshUnenrichedCount} model{refreshUnenrichedCount === 1 ? '' : 's'} without OpenRouter enrichment data — hidden from the table.
        </p>
      )}

      {/* Pool counts + reset */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {STAGES.map((s) => (
            <span key={s} className="rounded bg-muted px-2 py-0.5">
              {STAGE_LABELS[s]}: <strong className="text-foreground">{pools[s].size}</strong>
            </span>
          ))}
        </div>
        {filtersActive && (
          <button
            type="button"
            onClick={resetAllFilters}
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            Reset filters / sort
          </button>
        )}
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

      {/* Provider groups */}
      <div className="space-y-6">
        {PROVIDER_ORDER.map((providerKey) => {
          const providerModels = sortModels(filtered.filter((m) => m.provider === providerKey));
          if (providerModels.length === 0) return null;
          return (
            <section key={providerKey}>
              <h2 className="text-sm font-semibold text-foreground mb-2">
                {PROVIDER_LABELS[providerKey]}
              </h2>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40">
                    <tr className="align-bottom">
                      {/* Model column header — name filter */}
                      <th className="text-left px-3 py-2 font-medium text-xs text-muted-foreground">
                        <div className="flex flex-col gap-1.5">
                          <span>Model</span>
                          <input
                            type="text"
                            placeholder="filter by name…"
                            value={nameFilter}
                            onChange={(e) => setNameFilter(e.target.value)}
                            className="rounded border border-input bg-background px-2 py-1 text-xs font-normal outline-none focus:ring-1 focus:ring-ring w-44"
                          />
                        </div>
                      </th>
                      {/* Context column — sort + min-context filter */}
                      <th className="text-right px-3 py-2 font-medium text-xs text-muted-foreground whitespace-nowrap">
                        <div className="flex flex-col items-end gap-1.5">
                          <SortLabel label="Context" active={sortBy === 'context'} dir={sortDir} onClick={() => toggleSort('context')} />
                          <input
                            type="text"
                            placeholder="≥ tokens"
                            value={minContext}
                            onChange={(e) => setMinContext(e.target.value)}
                            className="rounded border border-input bg-background px-2 py-1 text-xs font-normal outline-none focus:ring-1 focus:ring-ring w-24 text-right"
                          />
                        </div>
                      </th>
                      {/* Price column — sort + max-price filter */}
                      <th className="text-right px-3 py-2 font-medium text-xs text-muted-foreground whitespace-nowrap">
                        <div className="flex flex-col items-end gap-1.5">
                          <SortLabel label="$/1M (in/out)" active={sortBy === 'price'} dir={sortDir} onClick={() => toggleSort('price')} />
                          <input
                            type="text"
                            placeholder="≤ $/1M in"
                            value={maxPrice}
                            onChange={(e) => setMaxPrice(e.target.value)}
                            className="rounded border border-input bg-background px-2 py-1 text-xs font-normal outline-none focus:ring-1 focus:ring-ring w-24 text-right"
                          />
                        </div>
                      </th>
                      {/* Capability columns — icon header, click icon to filter on this cap */}
                      {CAPABILITIES.map((cap) => {
                        const active = capFilters.has(cap.field);
                        return (
                          <th key={cap.field} className="text-center px-1.5 py-2 font-medium text-xs text-muted-foreground w-10">
                            <button
                              type="button"
                              title={`${cap.long}\nClick to filter to models with this capability`}
                              onClick={() => toggleCapFilter(cap.field)}
                              className={cn(
                                'inline-flex items-center justify-center rounded p-1 hover:bg-muted',
                                active && 'bg-primary/15 ring-1 ring-primary/40',
                              )}
                            >
                              <cap.icon className={cn('h-3.5 w-3.5', cap.color)} />
                            </button>
                          </th>
                        );
                      })}
                      {/* Stage columns — label + all required-cap icons */}
                      {STAGES.map((stage) => (
                        <th key={stage} className="text-center px-3 py-2 font-medium text-xs text-muted-foreground whitespace-nowrap">
                          <div className="flex flex-col items-center gap-1">
                            <span>{STAGE_LABELS[stage]}</span>
                            <div className="flex items-center gap-0.5">
                              {STAGE_REQUIREMENTS[stage].map((req, i) => (
                                <req.icon key={i} className={cn('h-3 w-3', req.color)} aria-label={`Requires ${req.label}`} />
                              ))}
                            </div>
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {providerModels.map((m) => (
                      <tr key={m.id} className="hover:bg-muted/30">
                        <td className="px-3 py-2 align-middle">
                          <span className="font-mono text-xs text-foreground block">{m.id}</span>
                          {m.name !== m.id && (
                            <span className="text-xs text-muted-foreground block mt-0.5">{m.name}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-middle text-right text-xs text-muted-foreground whitespace-nowrap">
                          {m.contextLength != null ? `${fmtCtx(m.contextLength)} tok` : '—'}
                        </td>
                        <td className="px-3 py-2 align-middle text-right text-xs text-muted-foreground font-mono whitespace-nowrap">
                          {m.promptPer1M != null
                            ? (m.promptPer1M === 0 && (m.completionPer1M ?? 0) === 0
                              ? 'Free'
                              : `$${fmtPrice(m.promptPer1M)} / $${fmtPrice(m.completionPer1M ?? 0)}`)
                            : '—'}
                        </td>
                        {/* Capability cells */}
                        {CAPABILITIES.map((cap) => (
                          <td
                            key={cap.field}
                            className="text-center px-1.5 py-2 align-middle"
                            title={m[cap.field] ? cap.long : `No ${cap.short.toLowerCase()}`}
                          >
                            {m[cap.field] ? (
                              <cap.icon className={cn('h-3.5 w-3.5 inline-block', cap.color)} />
                            ) : (
                              <span className="text-muted-foreground/30">—</span>
                            )}
                          </td>
                        ))}
                        {/* Stage checkbox cells */}
                        {STAGES.map((stage) => {
                          const checked = pools[stage].has(m.id);
                          const missing = missingReqs(m, stage);
                          const eligible = missing.length === 0;
                          const reasonText = !eligible
                            ? `Missing: ${missing.map((r) => r.label).join(', ')}`
                            : undefined;
                          return (
                            <td key={stage} className="px-3 py-2 text-center align-middle">
                              <label
                                title={reasonText}
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
