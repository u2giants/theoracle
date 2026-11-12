'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { LoadState } from './bits';
import { brainGet, brainPost } from './brain';

// Curated business functions (repair plan C1): the vocabulary the owner
// curates on this page — rename, merge, add and retire. C2's assignment
// tables point at it; one graph, function is an attribute.

type FunctionRow = {
  id: string;
  key: string;
  name: string;
  description: string;
  aliases: string[];
  parent_id: string | null;
  sort: number;
  active: boolean;
};

function aliasesText(aliases: string[]): string {
  return aliases.join('\n');
}

function lines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function FunctionEditForm({
  item,
  onSaved,
  onCancel,
}: {
  item: FunctionRow;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(item.name);
  const [description, setDescription] = useState(item.description);
  const [aliases, setAliases] = useState(aliasesText(item.aliases));
  const [sort, setSort] = useState(String(item.sort));
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      const response = await fetch(`/api/brain/functions/${encodeURIComponent(item.id)}`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          aliases: lines(aliases),
          sort: Number(sort),
        }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `edit failed (${response.status})`);
      }
      onSaved();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'edit failed');
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded border p-2" data-testid="function-edit-form">
      <label className="block text-sm">
        Name
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        Description
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <label className="block text-sm">
        Aliases (one per line)
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={3}
          value={aliases}
          onChange={(event) => setAliases(event.target.value)}
        />
      </label>
      <label className="block text-sm">
        Sort
        <input
          className="mt-1 w-24 rounded border px-2 py-1"
          type="number"
          value={sort}
          onChange={(event) => setSort(event.target.value)}
        />
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit" data-testid="function-save">
          Save
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} data-testid="function-cancel">
          Cancel
        </Button>
        {message && <span className="text-sm text-muted-foreground">{message}</span>}
      </div>
    </form>
  );
}

function AddFunctionForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [description, setDescription] = useState('');
  const [aliases, setAliases] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  function slugify(value: string): string {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await brainPost('functions', {
        key: key || slugify(name),
        name,
        description,
        aliases: lines(aliases),
      });
      setName('');
      setKey('');
      setDescription('');
      setAliases('');
      setMessage('Function added.');
      onAdded();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'could not add the function');
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded border p-4" data-testid="functions-add-form">
      <h2 className="font-semibold">Add a function</h2>
      <label className="block text-sm">
        Name
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            if (!key) setKey(slugify(event.target.value));
          }}
          required
        />
      </label>
      <label className="block text-sm">
        Key (stable slug)
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        Description
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <label className="block text-sm">
        Aliases (one per line)
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={3}
          value={aliases}
          onChange={(event) => setAliases(event.target.value)}
        />
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit" data-testid="function-add">
          Add function
        </Button>
        {message && <span className="text-sm text-muted-foreground">{message}</span>}
      </div>
    </form>
  );
}

export function FunctionsClient({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<FunctionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [mergeInto, setMergeInto] = useState<Record<string, string>>({});

  const [tick, setTick] = useState(0);
  const load = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    brainGet<{ functions: FunctionRow[] }>('functions')
      .then((body) => {
        if (!cancelled) {
          setRows(body.functions);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'could not load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  async function retire(id: string) {
    setMessage(null);
    try {
      await brainPost(`functions/${encodeURIComponent(id)}/retire`, {});
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'retire failed');
    }
  }

  async function merge(id: string) {
    setMessage(null);
    const into = mergeInto[id];
    if (!into) {
      setMessage('Pick the function to merge into first.');
      return;
    }
    try {
      await brainPost(`functions/${encodeURIComponent(id)}/merge`, { into });
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'merge failed');
    }
  }

  const targets = rows.filter((row) => row.active);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Company Map functions</h1>
          <p className="text-sm text-muted-foreground">
            The curated list of business functions. Sources, passages and things are assigned to
            these; the owner renames, merges, adds and retires them here.
          </p>
        </div>
        <Link className="text-sm underline" href="/map">
          Back to the map
        </Link>
      </header>
      <LoadState error={error} loading={loading} />
      {message && <p className="text-sm text-muted-foreground">{message}</p>}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Functions ({rows.length})</h2>
        <ul className="space-y-2 text-sm">
          {rows.map((item) => (
            <li
              key={item.id}
              className={`rounded border p-3 ${item.active ? '' : 'opacity-60'}`}
              data-testid="function-row"
              data-function-key={item.key}
              data-active={item.active ? 'active' : 'retired'}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="font-medium" data-testid="function-name">
                    {item.name}
                  </span>{' '}
                  <span className="text-xs text-muted-foreground" data-testid="function-key">
                    {item.key}
                  </span>
                  <div className="text-xs text-muted-foreground">Sort {item.sort}</div>
                </div>
                {isAdmin && (
                  <span className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      className="text-xs underline"
                      data-testid="function-edit"
                      onClick={() => setEditing(editing === item.id ? null : item.id)}
                    >
                      Rename / edit
                    </button>
                    {item.active && (
                      <button
                        type="button"
                        className="text-xs text-red-700 underline"
                        data-testid="function-retire"
                        onClick={() => retire(item.id)}
                      >
                        Retire
                      </button>
                    )}
                  </span>
                )}
              </div>
              <div className="mt-1 text-xs" data-testid="function-description">
                {item.description}
              </div>
              {item.aliases.length > 0 && (
                <div className="mt-1 text-xs text-muted-foreground" data-testid="function-aliases">
                  Aliases: {item.aliases.join(', ')}
                </div>
              )}
              {!item.active && (
                <div className="mt-1 text-xs text-muted-foreground" data-testid="function-status">
                  Retired
                  {item.parent_id
                    ? ' — merged into ' +
                      (rows.find((row) => row.id === item.parent_id)?.name ?? item.parent_id)
                    : ''}
                </div>
              )}
              {editing === item.id && isAdmin ? (
                <FunctionEditForm
                  item={item}
                  onSaved={() => {
                    setEditing(null);
                    load();
                  }}
                  onCancel={() => setEditing(null)}
                />
              ) : null}
              {isAdmin && item.active && (
                <div className="mt-2 flex items-center gap-2" data-testid="function-merge">
                  <select
                    className="rounded border px-2 py-1 text-xs"
                    value={mergeInto[item.id] ?? ''}
                    onChange={(event) =>
                      setMergeInto((prev) => ({ ...prev, [item.id]: event.target.value }))
                    }
                    data-testid="function-merge-target"
                  >
                    <option value="">Merge into…</option>
                    {targets
                      .filter((target) => target.id !== item.id)
                      .map((target) => (
                        <option key={target.id} value={target.id}>
                          {target.name}
                        </option>
                      ))}
                  </select>
                  <button
                    type="button"
                    className="text-xs underline"
                    data-testid="function-merge-submit"
                    onClick={() => merge(item.id)}
                  >
                    Merge
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
        {isAdmin && <AddFunctionForm onAdded={load} />}
      </section>
    </main>
  );
}
