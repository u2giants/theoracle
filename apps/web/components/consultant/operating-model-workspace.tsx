'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { OperatingModel } from '@/lib/operating-model-types';
import { WorkflowCanvas } from './workflow-canvas';
import { WorkflowFindings } from './workflow-findings';
import { ProcessAnalysisPanel } from './process-analysis-panel';
import { SourceDownload } from './source-download';

export function OperatingModelWorkspace() {
  const [token, setToken] = useState('');
  const [model, setModel] = useState<OperatingModel | null>(null);
  const [selected, setSelected] = useState('');
  const [page, setPage] = useState(0);
  const currentPath = useRef('/api/consultant/model');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);
  const load = useCallback(async (path = currentPath.current) => {
    currentPath.current = path;
    const generation = ++requestGeneration.current;
    try {
      let next = path;
      for (let attempt = 0; attempt < 30; attempt++) {
        const response = await fetch(next, { credentials: 'same-origin', cache: 'no-store' });
        const data = await response.json();
        if (generation !== requestGeneration.current) return;
        if (!response.ok) throw new Error(data.error ?? 'Could not load operating model');
        if (data.state === 'pending') {
          const poll = new URL(path, window.location.origin);
          poll.searchParams.set('runId', data.runId);
          next = poll.pathname + poll.search;
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
  const refresh = (path = currentPath.current) => {
    setLoading(true); setError(null); setModel(null);
    return load(path);
  };
  const invalidate = useCallback(() => { requestGeneration.current++; }, []);
  const login = async () => {
    try {
      const response = await fetch('/api/consultant/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }), credentials: 'same-origin' });
      setToken('');
      if (!response.ok) throw new Error('Session exchange failed');
      await refresh();
    } catch { setToken(''); setModel(null); setError('Could not connect.'); }
  };
  useEffect(() => { void load(); return invalidate; }, [load, invalidate]);
  return <main className="mx-auto max-w-6xl space-y-6 p-8">
    <div className="flex items-center justify-between"><h1 className="text-2xl font-semibold">Operating model</h1><button className="rounded border px-3 py-2" onClick={() => void refresh()}>Refresh</button></div>
    {!model && <div className="flex gap-2"><input type="password" aria-label="Access token" autoComplete="off" className="rounded border p-2" value={token} onChange={event => setToken(event.target.value)} /><button className="rounded bg-slate-900 px-4 py-2 text-white" onClick={() => void login()}>Connect</button></div>}
    {loading && <p role="status">Loading…</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {model && <>
      {model.state !== 'ready' && <p className="rounded bg-amber-50 p-4">{model.error ?? model.coverage_state ?? 'Operating model is unavailable.'}</p>}
      <div><label htmlFor="process">Process</label><select id="process" className="ml-2 rounded border p-2" value={selected} onChange={event => { const value = event.target.value; setSelected(value); setPage(0); void refresh(value ? `/api/consultant/processes/${encodeURIComponent(value)}` : '/api/consultant/model'); }}><option value="">Company overview</option>{(model.processes ?? []).map(process => <option key={process.process_id} value={process.process_id}>{process.label}</option>)}</select></div>
      <p className="text-sm text-slate-600">{model.declared_population?.join(' · ')} · Coverage: {model.coverage_state}</p>
      {(model.objects?.length ?? 0) > 0 && <section className="rounded-xl border p-5"><h2 className="font-semibold">Roles, artifacts, and definitions</h2><ul className="mt-3 space-y-3">{model.objects?.map(object => <li key={object.object_id}><span>{object.label} · {object.kind.replaceAll('_', ' ')} · {object.scope}</span><details><summary>Source support</summary>{object.support.observation_ids.flatMap(id => model.observations?.find(o => o.observation_id === id)?.evidence ?? []).map((quote,index) => <blockquote className="my-2 border-l-2 pl-3" key={index}>{quote.quote}<small className="block">Source {quote.ref.source_id}, revision {quote.ref.revision}</small></blockquote>)}</details></li>)}</ul></section>}
      {(model.interfaces?.length ?? 0) > 0 && <section className="rounded-xl border p-5"><h2 className="font-semibold">Process handoffs</h2><ul className="mt-3 space-y-3">{model.interfaces?.map(handoff => <li key={handoff.interface_id}>{handoff.from_process} → {handoff.to_process} · {handoff.artifact_id} · {handoff.status}<details><summary>Source support</summary>{handoff.support.observation_ids.flatMap(id => model.observations?.find(o => o.observation_id === id)?.evidence ?? []).map((quote,index) => <blockquote className="my-2 border-l-2 pl-3" key={index}>{quote.quote}</blockquote>)}</details></li>)}</ul>{selected && <button className="mt-3 rounded border px-3 py-2" onClick={() => void refresh(`/api/consultant/processes/${encodeURIComponent(selected)}?connected=1`)}>Show connected processes</button>}</section>}
      {!selected && (page > 0 || model.continuation) && <nav aria-label="Overview pages" className="flex gap-3"><button className="rounded border px-3 py-2" disabled={page === 0} onClick={() => { const previous = page - 1; setPage(previous); void refresh(`/api/consultant/model?page=${previous}`); }}>Previous</button><span>Page {page + 1}</span><button className="rounded border px-3 py-2" disabled={!model.continuation} onClick={() => { if (!model.continuation) return; const next = model.continuation.page; setPage(next); void refresh(`/api/consultant/model?page=${next}`); }}>Next</button></nav>}
      <div className="grid gap-6 lg:grid-cols-2">{(model.workflows ?? []).map(workflow => <WorkflowCanvas key={workflow.workflow_id} workflow={workflow} observations={model.observations} />)}</div>
      <SourceDownload />
      <ProcessAnalysisPanel analysis={model.analysis} />
      <WorkflowFindings findings={model.findings} quarantine={model.reviewer_quarantine} />
      {(model.finding_review_events?.length ?? 0)>0 && <section className="rounded-xl border p-5"><h2 className="font-semibold">Authorized review history</h2><p className="text-sm text-slate-600">Review decisions do not establish company policy.</p>{model.finding_review_events?.map(event=><article key={event.event_id} className="mt-3"><p>{event.action} · {event.scope}</p><p>{event.note}</p></article>)}</section>}
    </>}
  </main>;
}
