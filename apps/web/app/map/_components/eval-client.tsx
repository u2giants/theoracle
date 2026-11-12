'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { LoadState } from './bits';
import { brainGet, brainPost } from './brain';

// Evaluation page (plan step 11): admins write the cross-source questions;
// everyone sees runs over time, the per-question table and the change
// against the previous run.

type Question = {
  id: string;
  question: string;
  expected_points: string[];
  expected_source_titles: string[];
  author: string;
  approved_at: string | null;
  retired_at: string | null;
  abstention: boolean;
  recommendation: string | null;
  function: string[];
};

type Result = {
  question_id: string;
  question: string;
  expected_points: string[];
  expected_sources: string[];
  score: number;
  score_legacy: number;
  covered: number[];
  missing: number[];
  contradicted: number[];
  cited_sources: string[];
  expected_sources_cited: string[];
  mode_used: string | null;
  answer_md: string;
  error: string | null;
};

type Diff = { question: string; score: number; previous: number | null; delta: number | null };

type Run = {
  id: string;
  created_at: string;
  graph_version: number;
  mean_score: number;
  mean_score_legacy: number | null;
  previous_mean: number | null;
  mean_delta: number | null;
  results: Result[];
  diff: Diff[];
};

type Runs = {
  runs: Run[];
  latest_job: { state: string; error: string | null; created_at: string } | null;
};

const pct = (value: number) => `${Math.round(value * 100)}%`;

function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground">new</span>;
  if (Math.abs(value) < 0.005) return <span className="text-muted-foreground">±0</span>;
  const up = value > 0;
  return (
    <span className={up ? 'text-green-700' : 'text-red-700'}>
      {up ? '+' : '−'}
      {pct(Math.abs(value))}
    </span>
  );
}

function when(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

function lines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function commaList(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function QuestionForm({ onAdded }: { onAdded: () => void }) {
  const [question, setQuestion] = useState('');
  const [points, setPoints] = useState('');
  const [titles, setTitles] = useState('');
  const [functions, setFunctions] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await brainPost('eval/questions', {
        question,
        expected_points: lines(points),
        expected_source_titles: lines(titles),
        function: commaList(functions),
      });
      setQuestion('');
      setPoints('');
      setTitles('');
      setFunctions('');
      setMessage('Question added.');
      onAdded();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'could not add the question');
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded border p-4" data-testid="eval-form">
      <h2 className="font-semibold">Add a question</h2>
      <label className="block text-sm">
        Question
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        Expected points (3 to 6, one per line)
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={4}
          value={points}
          onChange={(event) => setPoints(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        Expected source titles (one per line)
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={3}
          value={titles}
          onChange={(event) => setTitles(event.target.value)}
        />
      </label>
      <label className="block text-sm">
        Functions (comma-separated; pre-filled from the question set)
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={functions}
          onChange={(event) => setFunctions(event.target.value)}
          data-testid="question-functions"
        />
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit">Add question</Button>
        {message && <span className="text-sm text-muted-foreground">{message}</span>}
      </div>
    </form>
  );
}

function QuestionEditForm({
  item,
  onSaved,
  onCancel,
}: {
  item: Question;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [question, setQuestion] = useState(item.question);
  const [points, setPoints] = useState(item.expected_points.join('\n'));
  const [titles, setTitles] = useState(item.expected_source_titles.join('\n'));
  const [functions, setFunctions] = useState((item.function ?? []).join(', '));
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      const response = await fetch(`/api/brain/eval/questions/${encodeURIComponent(item.id)}`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          question,
          expected_points: lines(points),
          expected_source_titles: lines(titles),
          abstention: item.abstention,
          recommendation: item.recommendation,
          function: commaList(functions),
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
    <form onSubmit={submit} className="space-y-2 rounded border p-2" data-testid="question-edit-form">
      <label className="block text-sm">
        Question
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        Expected points (3 to 6, one per line)
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={4}
          value={points}
          onChange={(event) => setPoints(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm">
        Expected source titles (one per line)
        <textarea
          className="mt-1 w-full rounded border px-2 py-1"
          rows={3}
          value={titles}
          onChange={(event) => setTitles(event.target.value)}
        />
      </label>
      <label className="block text-sm">
        Functions (comma-separated)
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={functions}
          onChange={(event) => setFunctions(event.target.value)}
          data-testid="question-functions"
        />
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit" data-testid="question-save">
          Save
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} data-testid="question-cancel">
          Cancel
        </Button>
        {message && <span className="text-sm text-muted-foreground">{message}</span>}
      </div>
    </form>
  );
}

function QuestionStatus({ item }: { item: Question }) {
  if (item.retired_at) {
    return (
      <span className="text-xs text-muted-foreground" data-testid="question-status">
        Retired {when(item.retired_at)} — does not count toward the eval bar
      </span>
    );
  }
  if (item.approved_at) {
    return (
      <span className="text-xs text-green-700" data-testid="question-status">
        Approved {when(item.approved_at)} — counts toward the eval bar
      </span>
    );
  }
  return (
    <span className="text-xs text-muted-foreground" data-testid="question-status">
      Draft — does not count toward the eval bar yet
    </span>
  );
}

function RunTable({ run }: { run: Run }) {
  const deltas = new Map(run.diff.map((item) => [item.question, item.delta]));
  return (
    <table className="w-full text-left text-sm" data-testid="eval-results">
      <thead>
        <tr className="border-b">
          <th className="py-1 pr-2">Question</th>
          <th className="py-1 pr-2">Score</th>
          <th className="py-1 pr-2">vs previous</th>
          <th className="py-1 pr-2">Missing points</th>
          <th className="py-1">Expected sources cited</th>
        </tr>
      </thead>
      <tbody>
        {run.results.map((item) => (
          <tr key={item.question_id} className="border-b align-top">
            <td className="py-1 pr-2">
              {item.question}
              {item.error && <div className="text-xs text-red-700">{item.error}</div>}
            </td>
            <td className="py-1 pr-2 font-medium">
              {item.error ? (
                <span className="text-red-700">error</span>
              ) : (
                <>
                  {pct(item.score)}
                  <span
                    className="ml-1 text-xs font-normal text-muted-foreground"
                    data-testid="eval-score-legacy"
                  >
                    legacy {pct(item.score_legacy)}
                  </span>
                </>
              )}
            </td>
            <td className="py-1 pr-2">
              <Delta value={deltas.get(item.question) ?? null} />
            </td>
            <td className="py-1 pr-2 text-xs">
              {[...item.missing, ...item.contradicted].length === 0
                ? '—'
                : [
                    ...item.missing.map((index) => item.expected_points[index]),
                    ...item.contradicted.map(
                      (index) => `${item.expected_points[index]} (contradicted)`,
                    ),
                  ].join('; ')}
            </td>
            <td className="py-1 text-xs">
              {item.expected_sources_cited.length} / {item.expected_sources.length}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function EvalClient({ isAdmin }: { isAdmin: boolean }) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [runs, setRuns] = useState<Runs | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const [tick, setTick] = useState(0);
  const load = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      brainGet<{ questions: Question[] }>('eval/questions'),
      brainGet<Runs>('eval/runs'),
    ])
      .then(([qs, rs]) => {
        if (cancelled) return;
        setQuestions(qs.questions);
        setRuns(rs);
        setError(null);
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

  async function runNow() {
    setMessage(null);
    try {
      const body = await brainPost<{ queued: boolean; detail?: string }>('eval/run', {});
      setMessage(body.queued ? 'Eval run queued.' : (body.detail ?? 'already queued'));
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'could not queue the run');
    }
  }

  async function remove(id: string) {
    try {
      const response = await fetch(`/api/brain/eval/questions/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(`delete failed (${response.status})`);
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'delete failed');
    }
  }

  async function approve(id: string) {
    setMessage(null);
    try {
      await brainPost(`eval/questions/${encodeURIComponent(id)}/approve`, {});
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'approve failed');
    }
  }

  async function retire(id: string) {
    setMessage(null);
    try {
      await brainPost(`eval/questions/${encodeURIComponent(id)}/retire`, {});
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'retire failed');
    }
  }

  const list = runs?.runs ?? [];
  const current = list.find((run) => run.id === selected) ?? list[0] ?? null;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Company Map evaluation</h1>
          <p className="text-sm text-muted-foreground">
            Questions with the points a good answer must contain. Each run answers every question
            and grades the answer.
          </p>
        </div>
        <Link className="text-sm underline" href="/map">
          Back to the map
        </Link>
      </header>
      <LoadState error={error} loading={loading} />

      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">Runs</h2>
          {isAdmin && (
            <Button variant="outline" onClick={runNow}>
              Run evaluation
            </Button>
          )}
          {message && <span className="text-sm text-muted-foreground">{message}</span>}
          {runs?.latest_job && runs.latest_job.state !== 'done' && (
            <span className="text-sm text-muted-foreground" data-testid="eval-job">
              Latest run: {runs.latest_job.state}
              {runs.latest_job.error ? ` (${runs.latest_job.error})` : ''}
            </span>
          )}
        </div>
        {!loading && list.length === 0 && (
          <p className="text-sm text-muted-foreground">No eval runs yet.</p>
        )}
        {list.length > 0 && (
          <table className="w-full text-left text-sm" data-testid="eval-runs">
            <thead>
              <tr className="border-b">
                <th className="py-1 pr-2">When (EST/EDT)</th>
                <th className="py-1 pr-2">Mean score</th>
                <th className="py-1 pr-2">vs previous</th>
                <th className="py-1 pr-2">Graph version</th>
                <th className="py-1">Questions</th>
              </tr>
            </thead>
            <tbody>
              {list.map((run) => (
                <tr
                  key={run.id}
                  className={`cursor-pointer border-b ${current?.id === run.id ? 'bg-muted' : ''}`}
                  onClick={() => setSelected(run.id)}
                >
                  <td className="py-1 pr-2">{when(run.created_at)}</td>
                  <td className="py-1 pr-2 font-medium">
                    <span data-testid="eval-mean">{pct(run.mean_score)}</span>
                    {run.mean_score_legacy !== null && (
                      <span
                        className="ml-1 text-xs font-normal text-muted-foreground"
                        data-testid="eval-mean-legacy"
                      >
                        legacy {pct(run.mean_score_legacy)}
                      </span>
                    )}
                  </td>
                  <td className="py-1 pr-2">
                    <Delta value={run.mean_delta} />
                  </td>
                  <td className="py-1 pr-2">{run.graph_version}</td>
                  <td className="py-1">{run.results.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {current && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Run of {when(current.created_at)}</h2>
          <RunTable run={current} />
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Questions ({questions.length})</h2>
        <ul className="space-y-2 text-sm">
          {questions.map((item) => (
            <li
              key={item.id}
              className={`rounded border p-3 ${item.retired_at ? 'opacity-60' : ''}`}
              data-testid="eval-question"
              data-question-id={item.id}
              data-status={item.retired_at ? 'retired' : item.approved_at ? 'approved' : 'draft'}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium">{item.question}</span>
                {isAdmin && (
                  <span className="flex shrink-0 items-center gap-2">
                    {!item.approved_at && !item.retired_at && (
                      <button
                        type="button"
                        className="text-xs text-green-700 underline"
                        data-testid="question-approve"
                        onClick={() => approve(item.id)}
                      >
                        Approve
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-xs underline"
                      data-testid="question-edit"
                      onClick={() => setEditing(editing === item.id ? null : item.id)}
                    >
                      Edit
                    </button>
                    {!item.retired_at && (
                      <button
                        type="button"
                        className="text-xs text-red-700 underline"
                        data-testid="question-retire"
                        onClick={() => retire(item.id)}
                      >
                        Retire
                      </button>
                    )}
                    {!item.approved_at && !item.retired_at && (
                      <button
                        type="button"
                        className="text-xs text-red-700 underline"
                        onClick={() => remove(item.id)}
                      >
                        Remove
                      </button>
                    )}
                  </span>
                )}
              </div>
              <QuestionStatus item={item} />
              {isAdmin && item.recommendation && (
                <div
                  className="mt-1 rounded bg-muted px-2 py-1 text-xs"
                  data-testid="question-recommendation"
                >
                  Recommended: {item.recommendation}
                </div>
              )}
              {item.abstention && (
                <div
                  className="mt-1 rounded bg-muted px-2 py-1 text-xs italic"
                  data-testid="question-abstention"
                >
                  The documents do not say — the correct answer admits ignorance.
                </div>
              )}
              {editing === item.id && isAdmin ? (
                <QuestionEditForm
                  item={item}
                  onSaved={() => {
                    setEditing(null);
                    load();
                  }}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <>
                  <ul className="list-disc pl-5 text-xs">
                    {item.expected_points.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                  {item.expected_source_titles.length > 0 && (
                    <div className="text-xs text-muted-foreground">
                      Sources: {item.expected_source_titles.join(', ')}
                    </div>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
        {isAdmin && <QuestionForm onAdded={load} />}
      </section>
    </main>
  );
}
