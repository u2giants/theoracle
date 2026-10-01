'use client';

// Pilot workspace: upload → draft → correct → confirm → ask → cited answer.
import { useCallback, useEffect, useState } from 'react';

interface Block {
  blockId: string;
  blockIndex: number;
  text: string;
  spanStart: number;
  spanEnd: number;
}

interface Citation {
  sourceId: string;
  spanStart: number;
  spanEnd: number;
  quote: string;
}

interface Hypothetical {
  label: string;
  description: string;
  measure: string;
  missingInputs: string[];
}

interface Answer {
  answerText: string;
  citations: Citation[];
  hypothetical: Hypothetical | null;
  isEstablishedFact: boolean;
}

interface RunData {
  runId: string;
  answer: Answer | null;
  status: string;
}

function pilotHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'x-oracle2-pilot-token': process.env.NEXT_PUBLIC_ORACLE2_PILOT_TOKEN ?? '',
    'x-oracle2-actor-id': process.env.NEXT_PUBLIC_ORACLE2_PILOT_ACTOR ?? 'pilot-user',
  };
}

export function PilotWorkspace() {
  const [text, setText] = useState('');
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [connections, setConnections] = useState<Array<{ from: number; to: number }>>([]);
  const [status, setStatus] = useState<string>('');
  const [confirmed, setConfirmed] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Persist run/source so the answer survives a page refresh.
  useEffect(() => {
    const storedRunId = sessionStorage.getItem('oracle2-run-id');
    const storedSourceId = sessionStorage.getItem('oracle2-source-id');
    const storedDraftId = sessionStorage.getItem('oracle2-draft-id');
    if (storedSourceId) setSourceId(storedSourceId);
    if (storedDraftId) setDraftId(storedDraftId);
    if (storedRunId) {
      setRunId(storedRunId);
      fetch(`/api/consultant/runs/${storedRunId}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.answer) {
            setAnswer(data.answer);
            setConfirmed(true);
            setStatus('confirmed');
          }
        })
        .catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (runId) sessionStorage.setItem('oracle2-run-id', runId);
    if (sourceId) sessionStorage.setItem('oracle2-source-id', sourceId);
    if (draftId) sessionStorage.setItem('oracle2-draft-id', draftId);
  }, [runId, sourceId, draftId]);

  const upload = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch('/api/consultant/sources', {
        method: 'POST',
        headers: pilotHeaders(),
        body: JSON.stringify({ text, filename: 'pilot-process-table.txt', processName: 'Pilot process' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'upload failed');
      setSourceId(data.sourceId);
      setDraftId(data.draftId);
      setBlocks(data.blocks);
      setStatus('draft');
      setConfirmed(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'upload failed');
    } finally {
      setLoading(false);
    }
  }, [text]);

  const correct = useCallback(async () => {
    if (!draftId) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`/api/consultant/reviews/${draftId}`, {
        method: 'POST',
        headers: pilotHeaders(),
        body: JSON.stringify({ action: 'correct', connections }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'correction failed');
      setStatus('draft (corrected)');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'correction failed');
    } finally {
      setLoading(false);
    }
  }, [draftId, connections]);

  const confirm = useCallback(async () => {
    if (!draftId) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`/api/consultant/reviews/${draftId}`, {
        method: 'POST',
        headers: pilotHeaders(),
        body: JSON.stringify({ action: 'confirm', scope: 'process-map' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'confirmation failed');
      setConfirmed(true);
      setStatus('confirmed');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'confirmation failed');
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  const ask = useCallback(async () => {
    if (!sourceId || !question.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch('/api/consultant/questions', {
        method: 'POST',
        headers: pilotHeaders(),
        body: JSON.stringify({ question, sourceId, draftId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'question failed');
      setAnswer(data.answer);
      setRunId(data.runId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'question failed');
    } finally {
      setLoading(false);
    }
  }, [sourceId, question, draftId]);

  const loadRun = useCallback(async () => {
    if (!runId) return;
    setError(null);
    try {
      const res = await fetch(`/api/consultant/runs/${runId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'run not found');
      setAnswer(data.answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'load failed');
    }
  }, [runId]);

  return (
    <div data-testid="pilot-workspace" className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Oracle Pilot — Document to Consultation</h1>

      {error && (
        <div data-testid="error-banner" className="rounded border border-red-400 bg-red-50 p-3 text-red-800">
          {error}
        </div>
      )}

      <section>
        <h2 className="mb-2 text-lg font-semibold">1. Upload a process document</h2>
        <textarea
          data-testid="document-text"
          className="h-32 w-full rounded border p-2"
          placeholder="Paste process document text…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          data-testid="upload-btn"
          className="mt-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          onClick={upload}
          disabled={loading || !text.trim()}
        >
          Upload
        </button>
        {sourceId && <p data-testid="source-id" className="mt-1 text-sm text-gray-600">Source: {sourceId}</p>}
      </section>

      {blocks.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">2. Source-linked process draft</h2>
          <p data-testid="draft-status" className="mb-2 text-sm">Status: {status}</p>
          <ul className="space-y-1">
            {blocks.map((b) => (
              <li key={b.blockId} data-testid={`block-${b.blockIndex}`} className="rounded border p-2 text-sm">
                <span className="font-mono text-xs text-gray-500">[{b.spanStart}–{b.spanEnd}]</span>{' '}
                {b.text}
              </li>
            ))}
          </ul>
        </section>
      )}

      {blocks.length > 1 && !confirmed && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">3. Correct a connection</h2>
          <div className="flex gap-2">
            <select
              data-testid="conn-from"
              className="rounded border p-1"
              onChange={(e) => {
                const from = Number(e.target.value);
                const to = connections[0]?.to ?? 1;
                setConnections([{ from, to }]);
              }}
            >
              {blocks.map((b) => (
                <option key={b.blockId} value={b.blockIndex}>Step {b.blockIndex + 1}</option>
              ))}
            </select>
            <span className="self-center">→</span>
            <select
              data-testid="conn-to"
              className="rounded border p-1"
              onChange={(e) => {
                const to = Number(e.target.value);
                const from = connections[0]?.from ?? 0;
                setConnections([{ from, to }]);
              }}
            >
              {blocks.map((b) => (
                <option key={b.blockId} value={b.blockIndex}>Step {b.blockIndex + 1}</option>
              ))}
            </select>
            <button
              data-testid="correct-btn"
              className="rounded bg-amber-600 px-3 py-1 text-white disabled:opacity-50"
              onClick={correct}
              disabled={loading}
            >
              Apply correction
            </button>
            <button
              data-testid="confirm-btn"
              className="rounded bg-green-600 px-3 py-1 text-white disabled:opacity-50"
              onClick={confirm}
              disabled={loading}
            >
              Confirm draft
            </button>
          </div>
        </section>
      )}

      {confirmed && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">4. Ask a connected question</h2>
          <input
            data-testid="question-input"
            className="w-full rounded border p-2"
            placeholder="e.g. Where can the handoff between licensing and production fail?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <button
              data-testid="ask-btn"
              className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              onClick={ask}
              disabled={loading || !question.trim()}
            >
              Ask
            </button>
            {runId && (
              <button
                data-testid="refresh-btn"
                className="rounded border px-4 py-2"
                onClick={loadRun}
              >
                Refresh answer
              </button>
            )}
          </div>
        </section>
      )}

      {answer && (
        <section data-testid="answer-section">
          <h2 className="mb-2 text-lg font-semibold">Answer</h2>
          <div data-testid="answer-text" className="whitespace-pre-wrap rounded border p-3">
            {answer.answerText}
          </div>
          {answer.citations.length > 0 && (
            <div data-testid="citations" className="mt-2">
              <h3 className="font-semibold">Citations</h3>
              <ul className="space-y-1">
                {answer.citations.map((c, i) => (
                  <li key={i} data-testid={`citation-${i}`} className="rounded bg-gray-50 p-2 text-sm">
                    <span className="font-mono text-xs">[{c.spanStart}–{c.spanEnd}]</span> {c.quote}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {answer.hypothetical && (
            <div data-testid="hypothetical" className="mt-2 rounded border border-dashed border-amber-400 bg-amber-50 p-3">
              <h3 className="font-semibold">{answer.hypothetical.label}</h3>
              <p className="text-sm">{answer.hypothetical.description}</p>
              <p className="mt-1 text-sm"><strong>Measure:</strong> {answer.hypothetical.measure}</p>
              <p className="text-sm"><strong>Missing inputs:</strong> {answer.hypothetical.missingInputs.join(', ')}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
