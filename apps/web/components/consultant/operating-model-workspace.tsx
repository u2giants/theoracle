'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { OperatingModel } from '@/lib/operating-model-types';
import { WorkflowCanvas } from './workflow-canvas';
import { WorkflowFindings } from './workflow-findings';
import { ProcessAnalysisPanel } from './process-analysis-panel';

export function OperatingModelWorkspace() {
  const [token, setToken] = useState('');
  const [model, setModel] = useState<OperatingModel | null>(null);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);
  const load = useCallback(async (path = '/api/consultant/model') => {
    const generation = ++requestGeneration.current;
    setLoading(true); setError(null); setModel(null);
    try {
      let next = path;
      for (let attempt = 0; attempt < 30; attempt++) {
        const response = await fetch(next, { credentials: 'same-origin', cache: 'no-store' });
        const data = await response.json();
        if (generation !== requestGeneration.current) return;
        if (!response.ok) throw new Error(data.error ?? 'Could not load operating model');
        if (data.state === 'pending') {
          next = `${path}?runId=${encodeURIComponent(data.runId)}`;
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        if (data.state === 'error') throw new Error('The operating model could not be verified.');
        setModel(data); return;
      }
      throw new Error('The view is taking longer than expected. Refresh to retry.');
    } catch (problem) {
      if (generation === requestGeneration.current) {
        setModel(null); setError(problem instanceof Error ? problem.message : 'Could not load operating model');
      }
    } finally { if (generation === requestGeneration.current) setLoading(false); }
  }, []);
  const login = async () => {
    try {
      const response = await fetch('/api/consultant/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }), credentials: 'same-origin' });
      setToken('');
      if (!response.ok) throw new Error('Session exchange failed');
      await load();
    } catch { setToken(''); setModel(null); setError('Could not connect.'); }
  };
  useEffect(() => { void load(); return () => { requestGeneration.current++; }; }, [load]);
  return <main className="mx-auto max-w-6xl space-y-6 p-8">
    <div className="flex items-center justify-between"><h1 className="text-2xl font-semibold">Operating model</h1><button className="rounded border px-3 py-2" onClick={() => void load()}>Refresh</button></div>
    {!model && <div className="flex gap-2"><input type="password" aria-label="Access token" autoComplete="off" className="rounded border p-2" value={token} onChange={event => setToken(event.target.value)} /><button className="rounded bg-slate-900 px-4 py-2 text-white" onClick={() => void login()}>Connect</button></div>}
    {loading && <p role="status">Loading…</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {model && <>
      {model.state !== 'ready' && <p className="rounded bg-amber-50 p-4">{model.error ?? model.coverage_state ?? 'Operating model is unavailable.'}</p>}
      <div><label htmlFor="process">Process</label><select id="process" className="ml-2 rounded border p-2" value={selected} onChange={event => { const value = event.target.value; setSelected(value); void load(value ? `/api/consultant/processes/${encodeURIComponent(value)}` : '/api/consultant/model'); }}><option value="">Company overview</option>{(model.processes ?? []).map(process => <option key={process.process_id} value={process.process_id}>{process.label}</option>)}</select></div>
      <div className="grid gap-6 lg:grid-cols-2">{(model.workflows ?? []).map(workflow => <WorkflowCanvas key={workflow.workflow_id} workflow={workflow} observations={model.observations} />)}</div>
      <ProcessAnalysisPanel analysis={model.analysis} />
      <WorkflowFindings findings={model.findings} quarantine={model.reviewer_quarantine} />
    </>}
  </main>;
}
