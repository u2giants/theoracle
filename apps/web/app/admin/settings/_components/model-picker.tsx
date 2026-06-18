'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Copy, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  CAPS,
  STAGE_REQUIREMENTS,
  meetsStageReq,
  missingReqs,
  type CapKey,
  type Stage,
} from '@/lib/stage-requirements';
import type { ReasoningEffort, AuxiliaryCapabilityFilter } from '@oracle/ai';

export type { ReasoningEffort };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// Mirrors the ModelInfo shape from /api/admin/models — includes the canonical
// capability fields that match the model-pool DB columns and the shared
// stage-requirements module.
type Model = {
  id: string;
  name: string;
  provider: string;
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  thinking: boolean;
  tools: boolean;
  structuredOutputs: boolean;
  promptCaching: boolean;
  outputCap: boolean;
  pdf: boolean;
};

type Status = 'idle' | 'saving' | 'saved' | 'error';

const EFFORT_OPTIONS: { value: ReasoningEffort; label: string }[] = [
  { value: 'off',    label: 'Off' },
  { value: 'low',    label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high',   label: 'High' },
];

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

function priceBadge(m: Model): string | null {
  if (m.promptPer1M == null) return null;
  if (m.promptPer1M === 0 && (m.completionPer1M ?? 0) === 0) return 'Free';
  return `$${fmtPrice(m.promptPer1M)} / $${fmtPrice(m.completionPer1M ?? 0)}`;
}

/**
 * Derive the pipeline stage from a settings key like 'default_interview_route'.
 * Only used for the 3 pipeline-role pickers — auxiliary-model pickers (vision,
 * general-purpose) pass an explicit `auxiliary` prop instead.
 */
function stageFromKey(settingKey: string): Stage {
  if (settingKey.includes('interview')) return 'interview';
  if (settingKey.includes('extraction')) return 'extraction';
  if (settingKey.includes('synthesis')) return 'synthesis';
  return 'interview';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Row of small capability icons for a model — used inside dropdown rows. */
function CapIcons({ model, size = 3 }: { model: Model; size?: number }) {
  const active = CAPS.filter((c) => (model as unknown as Record<CapKey, boolean>)[c.field]);
  if (active.length === 0) return null;
  return (
    <span className="flex items-center gap-0.5 shrink-0">
      {active.map((cap) => (
        <span key={cap.field} title={cap.long}>
          <cap.icon className={cn(`size-${size}`, cap.color)} />
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
        {CAPS.map((cap) => (
          <span key={cap.field} className="flex items-center gap-1 text-xs text-muted-foreground" title={cap.long}>
            <cap.icon className={cn('size-3', cap.color)} />
            {cap.short}
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
  currentResolvedModel,
  currentEffort,
  settingKey,
  settingDescription,
  effortSettingKey,
  effortSettingDescription,
  clipboardBrief,
  auxiliary,
}: {
  currentModel: string | null;
  currentResolvedModel?: string | null;
  currentEffort: ReasoningEffort | null;
  settingKey: string;
  settingDescription: string;
  /** Settings key for the reasoning-effort dropdown. Optional —
   *  if omitted, the effort selector is hidden entirely (e.g. for general-purpose
   *  picker where there's no stage to associate effort with). */
  effortSettingKey?: string;
  effortSettingDescription?: string;
  /** When provided, a "Copy job brief" button appears next to the Model label
   *  and copies this detailed role description to the clipboard — useful for
   *  pasting into a model-evaluation prompt or vendor comparison. */
  clipboardBrief?: string;
  /** Set for auxiliary-model pickers (vision, general-purpose). When present,
   *  the model list is fetched by the aux id and filtered by its single
   *  required capability (if any) rather than by pipeline-stage requirements. */
  auxiliary?: { id: string; requiredCapability?: AuxiliaryCapabilityFilter };
}) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>(
    currentModel ?? 'anthropic/claude-sonnet-4.6',
  );
  const [effort, setEffort] = useState<ReasoningEffort>(currentEffort ?? 'medium');
  const [status, setStatus] = useState<Status>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [briefCopied, setBriefCopied] = useState(false);

  async function copyBrief() {
    if (!clipboardBrief) return;
    try {
      await navigator.clipboard.writeText(clipboardBrief);
      setBriefCopied(true);
      setTimeout(() => setBriefCopied(false), 2500);
    } catch {
      // Clipboard API unavailable (insecure context / denied) — no-op.
    }
  }

  // Dropdown open state + search filter.
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Pipeline pickers filter by stage requirements; auxiliary pickers filter by
  // a single capability (or not at all). `stage` is null for auxiliary models.
  const stage: Stage | null = auxiliary ? null : stageFromKey(settingKey);
  const modelListParam = auxiliary ? auxiliary.id : (stage as Stage);

  useEffect(() => {
    let cancelled = false;
    async function loadModels() {
      try {
        const res = await fetch(`/api/admin/models?stage=${modelListParam}`);
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`${res.status}: ${body}`);
        }
        const data = (await res.json()) as { models: Model[] };
        if (!cancelled) {
          setModels(data.models);
          // Prefer the saved value when it's directly a pool model. Otherwise, if
          // it's a curated route ID that resolves to a pool model, select that
          // resolved model so the dropdown shows the concrete model (with its
          // capabilities + price) rather than an unmatched route string.
          if (currentModel && data.models.some((m) => m.id === currentModel)) {
            setSelected(currentModel);
          } else if (
            currentResolvedModel &&
            data.models.some((m) => m.id === currentResolvedModel)
          ) {
            setSelected(currentResolvedModel);
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
  }, [currentModel, currentResolvedModel, modelListParam]);

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
      // Preserve the canonical curated-route value when the admin hasn't actually
      // changed the model: if the saved value is a route ID (not itself a pool
      // model) and the current selection still equals the model it resolves to,
      // write the original route ID back rather than silently flattening it to a
      // bare model ID. Explicitly picking a different model writes that model ID.
      const valueToSave =
        currentModel && !savedModel && selected === currentResolvedModel
          ? currentModel
          : selected;

      // Save model selection.
      const res = await fetch('/api/admin/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: settingKey,
          value: valueToSave,
          description: settingDescription,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);

      // Save effort selection if applicable (and the selected model supports reasoning).
      if (effortSettingKey && selectedModel?.thinking) {
        const r2 = await fetch('/api/admin/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            key: effortSettingKey,
            value: effort,
            description: effortSettingDescription ?? `Reasoning effort for ${settingKey}.`,
          }),
        });
        if (!r2.ok) throw new Error(`${r2.status}: ${await r2.text()}`);
      }

      setStatus('saved');
      setTimeout(() => setStatus('idle'), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setStatus('error');
    }
  }

  const selectedModel = models.find((m) => m.id === selected);
  const savedModel = currentModel ? models.find((m) => m.id === currentModel) : undefined;
  // When the saved value is a curated route ID (not itself a pool model), it
  // resolves at runtime to a concrete model. If that resolved model IS in the
  // pool, the setting is healthy — we surface a calm note rather than the amber
  // "outside the approved pool" warning, which is reserved for values that
  // resolve to nothing selectable (synthetic routes, models pulled from the pool).
  const resolvedModel =
    currentResolvedModel && currentResolvedModel !== currentModel
      ? models.find((m) => m.id === currentResolvedModel)
      : undefined;

  // Pipeline pickers use the same stage predicates as the model-pool page.
  // Auxiliary pickers filter by a single capability flag (or show all models
  // when the aux model declares no required capability).
  const auxCap = auxiliary?.requiredCapability;
  const compatible = (
    auxiliary
      ? auxCap
        ? models.filter((m) => m[auxCap])
        : models
      : models.filter((m) => meetsStageReq(m, stage as Stage))
  ).sort((a, b) => (a.promptPer1M ?? Infinity) - (b.promptPer1M ?? Infinity));

  const filtered = query.trim()
    ? compatible.filter(
        (m) =>
          m.id.toLowerCase().includes(query.toLowerCase()) ||
          m.name.toLowerCase().includes(query.toLowerCase()),
      )
    : compatible;

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading available models…</p>;
  }
  if (fetchError) {
    return <p className="text-sm text-destructive">Failed to load models: {fetchError}</p>;
  }

  // For stage pickers, find which requirements the *selected* model fails.
  // We use this to surface a small warning under the dropdown when an admin
  // somehow has a non-compliant model saved (e.g., from before stage reqs changed).
  const selectedMissing =
    selectedModel && !auxiliary ? missingReqs(selectedModel, stage as Stage) : [];
  const savedValueOutsidePicker = Boolean(currentModel && !savedModel && !resolvedModel);
  const savedValueIsCuratedRoute = Boolean(currentModel && !savedModel && resolvedModel);

  const effortApplicable = effortSettingKey && selectedModel?.thinking === true;

  return (
    <div className="space-y-4">

      {/* ── Model + effort dropdowns (side by side when effort is applicable) ─ */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <label className="text-sm font-medium leading-none">Model</label>
          {clipboardBrief && (
            <button
              type="button"
              onClick={copyBrief}
              title="Copy a detailed brief of this model's job — what it's fed, what's expected, and which capabilities it needs — to your clipboard"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {briefCopied ? <Check className="size-3.5 text-green-600" /> : <Copy className="size-3.5" />}
              {briefCopied ? 'Copied' : 'Copy job brief'}
            </button>
          )}
        </div>

        <div className="flex items-start gap-2">
          {/* Model dropdown */}
          <div className="relative flex-1 min-w-0" ref={dropdownRef}>
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
                  {filtered.length} of {compatible.length} compatible models
                </div>
              </div>
            )}
          </div>

          {/* Effort dropdown (only when this is a stage picker AND selected model supports reasoning) */}
          {effortApplicable && (
            <div className="w-32 shrink-0">
              <select
                value={effort}
                onChange={(e) => { setEffort(e.target.value as ReasoningEffort); setStatus('idle'); }}
                title="Reasoning effort — translated per-provider (Anthropic budget_tokens, OpenAI reasoning_effort, Vertex thinkingBudget)"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm
                           ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                {EFFORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    Effort: {opt.label}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Warning if the saved model fails the stage's current requirements */}
        {selectedMissing.length > 0 && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            ⚠ Selected model doesn&apos;t meet this stage&apos;s requirements:{' '}
            {selectedMissing.map((r) => r.label).join(', ')}
          </p>
        )}
        {savedValueOutsidePicker && (
          <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <p className="font-medium">Saved value is not in this dropdown&apos;s approved model pool.</p>
            <p className="mt-1">
              Saved setting:{' '}
              <code className="font-mono">{currentModel}</code>
              {currentResolvedModel && currentResolvedModel !== currentModel && (
                <>
                  {' '}
                  resolves at runtime to{' '}
                  <code className="font-mono">{currentResolvedModel}</code>.
                </>
              )}
            </p>
            <p className="mt-1">
              Choose a model from the dropdown and save to bring production back in
              sync with the approved pool.
            </p>
          </div>
        )}
        {savedValueIsCuratedRoute && (
          <p className="text-xs text-muted-foreground">
            Saved as curated route <code className="font-mono">{currentModel}</code> — resolves to{' '}
            <code className="font-mono">{currentResolvedModel}</code>, shown selected above. Saving
            without changing the model keeps the curated route.
          </p>
        )}
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
          {CAPS.some((c) => (selectedModel as unknown as Record<CapKey, boolean>)[c.field]) && (
            <div className="flex flex-wrap gap-2 pt-0.5">
              {CAPS.filter((c) => (selectedModel as unknown as Record<CapKey, boolean>)[c.field]).map((cap) => (
                <span
                  key={cap.field}
                  title={cap.long}
                  className="flex items-center gap-1 text-xs text-muted-foreground"
                >
                  <cap.icon className={cn('size-3', cap.color)} />
                  {cap.short}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Save button ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={status === 'saving'} size="sm">
          {status === 'saving' ? 'Saving…' : effortApplicable ? 'Save model + effort' : 'Save model'}
        </Button>
        {status === 'saved' && (
          <span className="text-sm text-green-600">Saved.</span>
        )}
        {status === 'error' && saveError && (
          <span className="text-sm text-destructive">{saveError}</span>
        )}
      </div>

      {currentModel && currentModel !== selected && selected !== currentResolvedModel && status === 'idle' && (
        <p className="text-xs text-muted-foreground">
          Active model: <code className="font-mono">{currentModel}</code>
        </p>
      )}

      {/* ── Icon legend ───────────────────────────────────────────────────── */}
      <Legend />
    </div>
  );
}

// Re-export the per-stage requirements + helpers so server components rendering
// the stage card headers can show the same icon set the picker filters by.
export { STAGE_REQUIREMENTS } from '@/lib/stage-requirements';
