'use client';

// Function assignment control (repair plan C2). Shows one source/entity's
// function rows with weight and origin; admins get a multi-select of the
// curated vocabulary with weight inputs and a Save button that writes
// origin='admin' rows (the assignment job never overwrites those).
import { useEffect, useState } from 'react';
import { brainGet, brainPut, type FunctionAssignment, type FunctionRow } from './brain';
import { LoadState } from './bits';

export function FunctionAssign({
  kind,
  itemId,
  initial,
  isAdmin,
}: {
  kind: 'sources' | 'entities';
  itemId: string;
  initial: FunctionAssignment[];
  isAdmin: boolean;
}) {
  const [saved, setSaved] = useState<FunctionAssignment[] | null>(null);
  const [vocabulary, setVocabulary] = useState<FunctionRow[] | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const rows = saved ?? initial;

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    brainGet<{ functions: FunctionRow[] }>('functions')
      .then((body) => {
        if (cancelled) return;
        setVocabulary(body.functions.filter((row) => row.active));
        const picked = new Set<string>();
        const weights: Record<string, number> = {};
        for (const row of body.functions) {
          const existing = initial.find((item) => item.key === row.key);
          if (existing) {
            picked.add(row.key);
            weights[row.key] = existing.weight;
          }
        }
        setChecked(picked);
        setDraft(weights);
      })
      .catch(() => setVocabulary([]));
    return () => {
      cancelled = true;
    };
  }, [isAdmin, initial]);

  function toggle(key: string) {
    setChecked((previous) => {
      const next = new Set(previous);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
        if (draft[key] === undefined) setDraft((d) => ({ ...d, [key]: 0.5 }));
      }
      return next;
    });
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        functions: [...checked].map((key) => ({ key, weight: draft[key] ?? 0.5 })),
      };
      const body = await brainPut<{ functions: FunctionAssignment[] }>(
        `${kind}/${encodeURIComponent(itemId)}/functions`,
        payload,
      );
      setSaved(body.functions);
      setMessage('Saved.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded border p-3" data-testid="function-assign">
      <h3 className="text-sm font-semibold">Functions</h3>
      {rows.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {rows.map((row) => (
            <li
              key={row.key}
              className="flex flex-wrap items-center gap-2 text-sm"
              data-testid="function-assign-row"
              data-function-key={row.key}
            >
              <span className="font-medium">{row.name}</span>
              <span className="text-xs text-muted-foreground">
                weight {row.weight.toFixed(2)}
              </span>
              <span
                className="rounded bg-slate-100 px-1 text-xs text-muted-foreground"
                data-testid="function-assign-origin"
              >
                {row.origin}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No functions assigned yet.</p>
      )}
      {isAdmin ? (
        <div className="mt-3 space-y-2">
          {vocabulary === null ? (
            <LoadState error={null} loading />
          ) : (
            <ul className="space-y-1">
              {vocabulary.map((row) => (
                <li
                  key={row.key}
                  className="flex flex-wrap items-center gap-2 text-sm"
                  data-testid="function-assign-option"
                  data-function-key={row.key}
                >
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={checked.has(row.key)}
                      onChange={() => toggle(row.key)}
                      data-testid="function-assign-check"
                    />
                    {row.name}
                  </label>
                  {checked.has(row.key) && (
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.1}
                      className="w-20 rounded border px-1 py-0.5"
                      aria-label={`weight for ${row.name}`}
                      data-testid="function-assign-weight"
                      value={draft[row.key] ?? 0.5}
                      onChange={(event) =>
                        setDraft((d) => ({ ...d, [row.key]: Number(event.target.value) }))
                      }
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded bg-slate-900 px-3 py-1 text-sm text-white"
              onClick={save}
              disabled={saving}
              data-testid="function-assign-save"
            >
              Save functions
            </button>
            {message && (
              <span className="text-sm text-muted-foreground" data-testid="function-assign-message">
                {message}
              </span>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
