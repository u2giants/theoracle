'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Brain,
  Check,
  ChevronDown,
  Eye,
  FileText,
  ImageIcon,
  Search,
  Wrench,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Model = {
  id: string;
  name: string;
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  tools: boolean;
  files: boolean;
  reasoning: boolean;
  imageGen: boolean;
};

type Status = 'idle' | 'saving' | 'saved' | 'error';

// ---------------------------------------------------------------------------
// Capability icon definitions — single source of truth for icons + legend
// ---------------------------------------------------------------------------

const CAPS = [
  {
    key: 'vision'    as const,
    Icon: Eye,
    color: 'text-blue-500',
    label: 'Vision',
    desc: 'Accepts image input',
  },
  {
    key: 'tools'     as const,
    Icon: Wrench,
    color: 'text-emerald-500',
    label: 'Tool use',
    desc: 'Supports function / tool calling',
  },
  {
    key: 'files'     as const,
    Icon: FileText,
    color: 'text-orange-500',
    label: 'File input',
    desc: 'Accepts documents (PDF, DOCX…)',
  },
  {
    key: 'reasoning' as const,
    Icon: Brain,
    color: 'text-purple-500',
    label: 'Reasoning',
    desc: 'Extended chain-of-thought / thinking',
  },
  {
    key: 'imageGen'  as const,
    Icon: ImageIcon,
    color: 'text-pink-500',
    label: 'Image gen',
    desc: 'Generates image output',
  },
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a per-1M-token price for display. */
function fmtPrice(n: number): string {
  if (n === 0) return '0';
  if (n < 0.001) return n.toFixed(5);
  if (n < 0.1) return n.toFixed(3);
  if (n < 1) return n.toFixed(2);
  return n.toFixed(2);
}

/** Format context window size — "200K", "1M", etc. */
function fmtCtx(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return n.toLocaleString();
}

/** Build the short price badge text shown inside each dropdown row. */
function priceBadge(m: Model): string | null {
  if (m.promptPer1M == null) return null;
  if (m.promptPer1M === 0 && (m.completionPer1M ?? 0) === 0) return 'Free';
  return `$${fmtPrice(m.promptPer1M)} / $${fmtPrice(m.completionPer1M ?? 0)}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Row of capability icons for a model. */
function CapIcons({ model, size = 3 }: { model: Model; size?: number }) {
  const active = CAPS.filter((c) => model[c.key]);
  if (active.length === 0) return null;
  return (
    <span className="flex items-center gap-0.5 shrink-0">
      {active.map(({ key, Icon, color, desc }) => (
        <span key={key} title={desc}>
          <Icon className={cn(`size-${size}`, color)} />
        </span>
      ))}
    </span>
  );
}

/** Icon legend — shown below the dropdown. */
function Legend() {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <p className="text-xs font-medium text-muted-foreground mb-1.5">Icon legend</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {CAPS.map(({ key, Icon, color, label, desc }) => (
          <span key={key} className="flex items-center gap-1 text-xs text-muted-foreground" title={desc}>
            <Icon className={cn('size-3', color)} />
            {label}
          </span>
        ))}
        <span className="flex items-center gap-1 text-xs text-muted-foreground" title="Cost per 1 million input / output tokens">
          <span className="font-mono text-[10px] text-muted-foreground">$/M</span>
          Price per 1M tokens (in&nbsp;/&nbsp;out)
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ModelPicker({
  currentModel,
  settingKey,
  settingDescription,
}: {
  currentModel: string | null;
  settingKey: string;
  settingDescription: string;
}) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>(
    currentModel ?? 'anthropic/claude-sonnet-4.6',
  );
  const [status, setStatus] = useState<Status>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);

  // Dropdown open state + search filter.
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Load models on mount.
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
          if (currentModel && data.models.some((m) => m.id === currentModel)) {
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
    return () => { cancelled = true; };
  }, [currentModel]);

  // Close on outside click.
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Focus search when dropdown opens.
  useEffect(() => {
    if (open) {
      setTimeout(() => searchRef.current?.focus(), 0);
    }
  }, [open]);

  async function save() {
    setStatus('saving');
    setSaveError(null);
    try {
      const res = await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: settingKey,
          value: selected,
          description: settingDescription,
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

  const filtered = query.trim()
    ? models.filter(
        (m) =>
          m.id.toLowerCase().includes(query.toLowerCase()) ||
          m.name.toLowerCase().includes(query.toLowerCase()),
      )
    : models;

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading available models…</p>;
  }
  if (fetchError) {
    return (
      <p className="text-sm text-destructive">Failed to load models: {fetchError}</p>
    );
  }

  return (
    <div className="space-y-4">

      {/* ── Dropdown ─────────────────────────────────────────────────────── */}
      <div className="space-y-2">
        <label className="text-sm font-medium leading-none">Model</label>

        <div className="relative" ref={dropdownRef}>
          {/* Trigger button */}
          <button
            type="button"
            onClick={() => { setOpen((v) => !v); }}
            disabled={status === 'saving'}
            className={cn(
              'w-full flex items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm',
              'ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            <span className="flex items-center gap-2 min-w-0">
              <span className="font-mono truncate">
                {selected || 'Select a model…'}
              </span>
              {selectedModel && <CapIcons model={selectedModel} />}
            </span>
            <ChevronDown className={cn('size-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
          </button>

          {/* Floating list */}
          {open && (
            <div className="absolute z-50 mt-1 w-full rounded-md border bg-background shadow-lg">
              {/* Search box */}
              <div className="flex items-center gap-2 border-b px-3 py-2">
                <Search className="size-3.5 shrink-0 text-muted-foreground" />
                <input
                  ref={searchRef}
                  type="text"
                  placeholder="Search models…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
              </div>

              {/* Model rows */}
              <ul className="max-h-72 overflow-y-auto py-1" role="listbox">
                {filtered.length === 0 && (
                  <li className="px-3 py-4 text-center text-sm text-muted-foreground">
                    No models match &ldquo;{query}&rdquo;
                  </li>
                )}
                {filtered.map((m) => {
                  const badge = priceBadge(m);
                  const isSelected = m.id === selected;
                  return (
                    <li key={m.id} role="option" aria-selected={isSelected}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected(m.id);
                          setStatus('idle');
                          setOpen(false);
                          setQuery('');
                        }}
                        className={cn(
                          'w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted',
                          isSelected && 'bg-muted/60',
                        )}
                      >
                        {/* Left: checkmark + model ID + capability icons */}
                        <span className="flex items-center gap-1.5 min-w-0">
                          <Check
                            className={cn(
                              'size-3.5 shrink-0',
                              isSelected ? 'text-foreground' : 'invisible',
                            )}
                          />
                          <span className="font-mono text-xs truncate">{m.id}</span>
                          <CapIcons model={m} size={3} />
                        </span>

                        {/* Right: price badge */}
                        {badge != null && (
                          <span
                            className={cn(
                              'shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px]',
                              badge === 'Free'
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-muted text-muted-foreground',
                            )}
                          >
                            {badge}
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="border-t px-3 py-1.5 text-[10px] text-muted-foreground">
                {filtered.length} of {models.length} models shown
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Selected model detail card ────────────────────────────────────── */}
      {selectedModel && (
        <div className="rounded-md border bg-muted/30 px-4 py-3 text-xs space-y-1.5">
          <p className="font-medium text-sm text-foreground">{selectedModel.name}</p>

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
            {selectedModel.contextLength != null && (
              <span>Context: {fmtCtx(selectedModel.contextLength)} tokens</span>
            )}
            {selectedModel.promptPer1M != null && (
              <span>
                {selectedModel.promptPer1M === 0 && (selectedModel.completionPer1M ?? 0) === 0
                  ? 'Free'
                  : `$${fmtPrice(selectedModel.promptPer1M)} in / $${fmtPrice(selectedModel.completionPer1M ?? 0)} out per 1M tokens`
                }
              </span>
            )}
          </div>

          {/* Active capabilities */}
          {CAPS.some((c) => selectedModel[c.key]) && (
            <div className="flex flex-wrap gap-2 pt-0.5">
              {CAPS.filter((c) => selectedModel[c.key]).map(({ key, Icon, color, label, desc }) => (
                <span
                  key={key}
                  title={desc}
                  className="flex items-center gap-1 text-xs text-muted-foreground"
                >
                  <Icon className={cn('size-3', color)} />
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Save button ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={status === 'saving'} size="sm">
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

      {/* ── Icon legend ───────────────────────────────────────────────────── */}
      <Legend />
    </div>
  );
}
