'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { LoadState } from './bits';
import { brainGet, brainPost, sourceHref } from './brain';

// Admin page for the open-question queue (plan step 12): open questions and
// who each will go to, asked/answered history, a pause switch per employee
// and the global on/off switch. The bot only ever writes to employees who
// messaged it first, and only while interviews are turned on.

type Question = {
  id: string;
  question: string;
  why: string;
  state: 'open' | 'asked' | 'answered' | 'dismissed';
  target_employee_id: string | null;
  target_name: string | null;
  next_target: { employee_id: string; name: string } | null;
  asked_at: string | null;
  answer: string | null;
  answered_at: string | null;
  answer_source_id: string | null;
  created_at: string | null;
};

type Employee = {
  employee_id: string;
  name: string;
  paused: boolean;
  connected: boolean;
  asked_last_7_days: number;
};

type Overview = {
  env_enabled: boolean;
  switch_enabled: boolean;
  weekly_cap: number;
  questions: Question[];
  employees: Employee[];
};

function when(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/New_York',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

export function QuestionsClient() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const [reloads, setReloads] = useState(0);
  const load = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    brainGet<Overview>('interview/overview')
      .then((overview) => {
        if (cancelled) return;
        setData(overview);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'could not load questions');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloads]);

  async function act(path: string, payload: unknown, done: string) {
    setMessage(null);
    try {
      await brainPost(path, payload);
      setMessage(done);
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'action failed');
    }
  }

  const open = data?.questions.filter((q) => q.state === 'open') ?? [];
  const history = data?.questions.filter((q) => q.state !== 'open') ?? [];
  const connected = data?.employees.filter((e) => e.connected) ?? [];
  const on = Boolean(data?.env_enabled && data?.switch_enabled);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Open questions</h1>
        <Link className="text-sm underline" href="/map">
          Back to the map
        </Link>
      </header>
      <LoadState error={error} loading={loading} />
      {message && <p className="text-sm text-muted-foreground">{message}</p>}
      {data && (
        <>
          <section className="space-y-2 rounded border p-4" data-testid="interview-switch">
            <h2 className="font-semibold">Teams interviews: {on ? 'on' : 'off'}</h2>
            {!data.env_enabled && (
              <p className="text-sm text-muted-foreground">
                Turned off on the server. Nothing is sent until it is turned on there.
              </p>
            )}
            <p className="text-sm text-muted-foreground">
              Questions go only to people who messaged The Oracle bot first, at most{' '}
              {data.weekly_cap} per person per week.
            </p>
            <Button
              variant="outline"
              onClick={() =>
                act(
                  'interview/settings',
                  { enabled: !data.switch_enabled },
                  data.switch_enabled ? 'Interviews paused for everyone.' : 'Interviews switched on.',
                )
              }
            >
              {data.switch_enabled ? 'Pause for everyone' : 'Switch on'}
            </Button>
          </section>

          <section className="space-y-2">
            <h2 className="font-semibold">Waiting to be asked ({open.length})</h2>
            {open.length === 0 && <p className="text-sm text-muted-foreground">No open questions.</p>}
            <ul className="space-y-2" data-testid="open-questions">
              {open.map((q) => (
                <li key={q.id} className="space-y-1 rounded border p-3 text-sm">
                  <p className="font-medium">{q.question}</p>
                  <p className="text-muted-foreground">From: {q.why}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <span>
                      Goes to:{' '}
                      {q.next_target ? (
                        q.next_target.name
                      ) : (
                        <em>nobody reachable yet — pick someone</em>
                      )}
                    </span>
                    <select
                      className="rounded border px-1 py-0.5"
                      value={q.target_employee_id ?? ''}
                      onChange={(event) =>
                        act(
                          `interview/questions/${q.id}/route`,
                          { employee_id: event.target.value || null },
                          'Routing saved.',
                        )
                      }
                    >
                      <option value="">Automatic</option>
                      {connected.map((e) => (
                        <option key={e.employee_id} value={e.employee_id}>
                          {e.name}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => act(`interview/questions/${q.id}/dismiss`, {}, 'Question dismissed.')}
                    >
                      Dismiss
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-2">
            <h2 className="font-semibold">Asked and answered</h2>
            <table className="w-full text-left text-sm" data-testid="question-history">
              <thead>
                <tr className="border-b">
                  <th className="py-1 pr-2">Question</th>
                  <th className="py-1 pr-2">Asked</th>
                  <th className="py-1 pr-2">State</th>
                  <th className="py-1 pr-2">Answer</th>
                </tr>
              </thead>
              <tbody>
                {history.map((q) => (
                  <tr key={q.id} className="border-b align-top">
                    <td className="py-1 pr-2">{q.question}</td>
                    <td className="py-1 pr-2">
                      {q.target_name ?? ''} {when(q.asked_at)}
                    </td>
                    <td className="py-1 pr-2">{q.state}</td>
                    <td className="py-1 pr-2">
                      {q.answer}
                      {q.answer_source_id && (
                        <>
                          {' '}
                          <Link className="underline" href={sourceHref(q.answer_source_id)}>
                            source
                          </Link>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="space-y-2">
            <h2 className="font-semibold">People the bot can reach</h2>
            {connected.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Nobody yet. A person becomes reachable after they message The Oracle bot in Teams.
              </p>
            )}
            <ul className="space-y-1 text-sm" data-testid="interview-employees">
              {connected.map((e) => (
                <li key={e.employee_id} className="flex items-center gap-3">
                  <span className="min-w-48">{e.name}</span>
                  <span className="text-muted-foreground">{e.asked_last_7_days} asked this week</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      act(
                        `interview/employees/${e.employee_id}/pause`,
                        { paused: !e.paused },
                        e.paused ? `${e.name} resumed.` : `${e.name} paused.`,
                      )
                    }
                  >
                    {e.paused ? 'Resume' : 'Pause'}
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
