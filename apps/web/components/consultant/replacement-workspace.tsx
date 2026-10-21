'use client';

// Replacement workspace: the S03 U3–U5 browser journey over the offline
// fixture store. Shows the State 13 machine, original viewer, connection
// correction (no body edit), scoped confirmation, cancel with liability, and
// native1..N attempt visibility. Synthetic/invented only.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSessionValue } from '@/lib/use-session-value';
import {
  REPLACEMENT_STATES,
  REPLACEMENT_STATE_LABELS,
  type ReplacementState,
} from '@/lib/replacement-contract';

interface AttemptView {
  attemptId: string;
  attemptNumber: number;
  status: 'new' | 'spent' | 'retained';
  spentAt: string | null;
  liabilityPreserved: boolean;
  note: string;
}

interface CorrectionView {
  correctionId: string;
  transitionId: string;
  expectedFromId: string;
  expectedToId: string;
  newFromId: string;
  newToId: string;
  reason: string;
  baseVersion: number;
  resultingModelVersion: number;
  originalCorrectionSha256: string;
}

interface JourneyView {
  journeyId: string;
  journeyRevision: number;
  state: ReplacementState;
  message: string;
  model: { modelId: string; version: number; contentHash: string } | null;
  confirmation: { workflowId: string; version: number; contentHash: string; current: boolean } | null;
  answer: { text: string; citations: Array<{ quote: string }> } | null;
  mapView: {
    workflow: {
      workflow_id: string;
      steps: Array<{ step_id: string; label: string }>;
      transitions: Array<{ transition_id: string; from_id: string; to_id: string }>;
    };
    findings: Array<{ finding_id: string; text: string; status: string }>;
  } | null;
  sources: Array<{ sourceId: string; revision: number; originalSha256: string }>;
  attempts?: AttemptView[];
  corrections?: CorrectionView[];
  invalidatedAt?: string | null;
}

async function parseJson(response: Response): Promise<Record<string, unknown>> {
  return (await response.json()) as Record<string, unknown>;
}

async function readJourney(journeyId: string, signal?: AbortSignal): Promise<JourneyView> {
  const response = await fetch(`/api/consultant/replacement/v1/journeys/${encodeURIComponent(journeyId)}`, {
    credentials: 'same-origin', cache: 'no-store', signal,
  });
  if (!response.ok) throw new Error('Could not retrieve the replacement journey');
  return response.json() as Promise<JourneyView>;
}

export function ReplacementWorkspace() {
  const savedSourceId = useSessionValue('oracle2-replacement-source');
  const savedSourceMeta = useSessionValue('oracle2-replacement-source-meta');
  const savedJourneyId = useSessionValue('oracle2-replacement-journey');
  const [chosenSourceId, setSourceId] = useState<string | null | undefined>(undefined);
  const sourceId = chosenSourceId === undefined ? savedSourceId : chosenSourceId;
  type SourceMeta = { originalSha256: string; hasStaleSeeded: boolean };
  const restoredMeta = useMemo<SourceMeta | null>(() => {
    if (!savedSourceId || !savedSourceMeta) return null;
    try {
      const value: unknown = JSON.parse(savedSourceMeta);
      if (value && typeof value === 'object' && 'originalSha256' in value && 'hasStaleSeeded' in value
          && typeof value.originalSha256 === 'string' && typeof value.hasStaleSeeded === 'boolean') {
        return { originalSha256: value.originalSha256, hasStaleSeeded: value.hasStaleSeeded };
      }
    } catch { /* Malformed refresh hints confer no authority. */ }
    return null;
  }, [savedSourceId, savedSourceMeta]);
  const [chosenSourceMeta, setSourceMeta] = useState<SourceMeta | null | undefined>(undefined);
  const sourceMeta = chosenSourceMeta === undefined ? restoredMeta : chosenSourceMeta;
  const [staleSeededLabel, setStaleSeededLabel] = useState('');
  const [journey, setJourney] = useState<JourneyView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [correctionReason, setCorrectionReason] = useState('Record an explicit handoff owner after authorized review.');

  const refresh = useCallback(async (journeyId: string) => {
    setJourney(await readJourney(journeyId));
  }, []);

  useEffect(() => {
    if (!savedJourneyId) return;
    const controller = new AbortController();
    readJourney(savedJourneyId, controller.signal)
      .then(data => { if (!controller.signal.aborted) setJourney(data); })
      .catch(() => {});
    return () => controller.abort();
  }, [savedJourneyId]);

  useEffect(() => {
    if (journey) sessionStorage.setItem('oracle2-replacement-journey', journey.journeyId);
    if (sourceId) sessionStorage.setItem('oracle2-replacement-source', sourceId);
    if (sourceMeta) {
      sessionStorage.setItem('oracle2-replacement-source-meta', JSON.stringify(sourceMeta));
    }
  }, [journey, sourceId, sourceMeta]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'request failed');
    } finally {
      setBusy(false);
    }
  };

  const onUpload = (event: React.ChangeEvent<HTMLInputElement>) =>
    run(async () => {
      const file = event.target.files?.[0];
      if (!file) return;
      const form = new FormData();
      form.append('file', file);
      if (staleSeededLabel) {
        form.append('staleSeededLabel', staleSeededLabel);
        form.append('staleSeededModelId', '00000000-0000-4000-8000-0000000000s1');
        form.append(
          'staleSeededContentHash',
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        );
      }
      const response = await fetch('/api/consultant/replacement/v1/sources', {
        method: 'POST',
        body: form,
        credentials: 'same-origin',
      });
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'upload failed'));
      setSourceId(String(data.sourceId));
      setSourceMeta({
        originalSha256: String(data.originalSha256),
        hasStaleSeeded: Boolean(data.hasStaleSeeded),
      });
    });

  const onCreateJourney = () =>
    run(async () => {
      if (!sourceId) throw new Error('upload a source first');
      const response = await fetch('/api/consultant/replacement/v1/journeys', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ sourceIds: [sourceId], idempotencyKey: `create-${sourceId}` }),
        credentials: 'same-origin',
      });
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'journey create failed'));
      setJourney(data as unknown as JourneyView);
    });

  const advance = (action: string) =>
    run(async () => {
      if (!journey) throw new Error('no journey');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/advance`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            action,
            expectedStateRevision: journey.journeyRevision,
          }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'advance failed'));
      await refresh(journey.journeyId);
    });

  const correct = () =>
    run(async () => {
      if (!journey?.model || !journey.mapView) throw new Error('no current model');
      const target = journey.mapView.workflow.transitions[0];
      if (!target) throw new Error('no transition to correct');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/corrections`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            baseVersion: journey.model.version,
            baseContentHash: journey.model.contentHash,
            transitionId: target.transition_id,
            expectedFromId: target.from_id,
            expectedToId: target.to_id,
            newFromId: 'step-2',
            newToId: 'step-3',
            reason: correctionReason,
            idempotencyKey: `corr-${journey.journeyId}-${journey.model.version}`,
            expectedJourneyRevision: journey.journeyRevision,
          }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'correction failed'));
      await refresh(journey.journeyId);
    });

  const confirmScope = () =>
    run(async () => {
      if (!journey?.model || !journey.mapView) throw new Error('no current model');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/confirmations`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            version: journey.model.version,
            contentHash: journey.model.contentHash,
            workflowId: journey.mapView.workflow.workflow_id,
            expectedJourneyRevision: journey.journeyRevision,
            idempotencyKey: `conf-${journey.journeyId}-${journey.model.version}`,
          }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'confirm failed'));
      await refresh(journey.journeyId);
    });

  const withdraw = () =>
    run(async () => {
      if (!journey) throw new Error('no journey');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/confirmations`,
        {
          method: 'DELETE',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ expectedJourneyRevision: journey.journeyRevision }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'withdraw failed'));
      await refresh(journey.journeyId);
    });

  const ask = () =>
    run(async () => {
      if (!journey) throw new Error('no journey');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/answers`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            intent: 'overview',
            expectedJourneyRevision: journey.journeyRevision,
            idempotencyKey: `ans-${journey.journeyId}-${journey.journeyRevision}`,
          }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'answer failed'));
      await refresh(journey.journeyId);
    });

  const cancel = () =>
    run(async () => {
      if (!journey) throw new Error('no journey');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/cancel`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            expectedStateRevision: journey.journeyRevision,
            idempotencyKey: `cancel-${journey.journeyId}`,
          }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'cancel failed'));
      await refresh(journey.journeyId);
    });

  const attemptOp = (op: 'dispatch' | 'spend' | 'replay', attemptId?: string) =>
    run(async () => {
      if (!journey) throw new Error('no journey');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/attempts`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ op, attemptId }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'attempt op failed'));
      await refresh(journey.journeyId);
    });

  const invalidate = () =>
    run(async () => {
      if (!journey) throw new Error('no journey');
      const response = await fetch(
        `/api/consultant/replacement/v1/journeys/${journey.journeyId}/advance`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            action: 'invalidate',
            expectedStateRevision: journey.journeyRevision,
          }),
          credentials: 'same-origin',
        },
      );
      const data = await parseJson(response);
      if (!response.ok) throw new Error(String(data.error ?? 'invalidate failed'));
      await refresh(journey.journeyId);
    });

  const currentState = journey?.state;
  const terminal =
    currentState === 'cancelled' ||
    currentState === 'failed_spent' ||
    currentState === 'error';
  const canLandDraft = currentState === 'processing';
  const canLandRevision = currentState === 'revision_pending';
  const canCorrect =
    currentState === 'draft_ready' ||
    currentState === 'confirmed_for_scope' ||
    currentState === 'answer_ready';
  const canConfirm = currentState === 'draft_ready';
  const canAsk = currentState === 'confirmed_for_scope';
  const canCancel = Boolean(currentState) && currentState !== 'cancelled';

  return (
    <div data-testid="replacement-workspace" className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold">Replacement journey (offline fixture)</h1>
      <p className="text-sm text-gray-600">
        Synthetic invented data only. Browser journey offline is not native acceptance.
      </p>

      {error && (
        <div data-testid="error-banner" className="rounded border border-red-400 bg-red-50 p-3 text-red-800">
          {error}
        </div>
      )}

      <section data-testid="state-machine" className="rounded border p-3">
        <h2 className="mb-2 font-medium">State machine</h2>
        <ul className="flex flex-wrap gap-2">
          {REPLACEMENT_STATES.map((state) => (
            <li
              key={state}
              data-testid={`state-${state}`}
              className={
                currentState === state
                  ? 'rounded bg-blue-600 px-2 py-1 text-xs text-white'
                  : 'rounded bg-gray-100 px-2 py-1 text-xs text-gray-700'
              }
            >
              {REPLACEMENT_STATE_LABELS[state]}
            </li>
          ))}
        </ul>
        <p data-testid="current-state" className="mt-2 text-sm">
          Current state: {currentState ?? 'none'}
        </p>
        <p data-testid="state-message" className="text-sm text-gray-600">
          {journey?.message ?? ''}
        </p>
        <p data-testid="state-revision" className="text-sm text-gray-600">
          Revision: {journey?.journeyRevision ?? 0}
        </p>
      </section>

      <section data-testid="upload-section" className="rounded border p-3">
        <h2 className="mb-2 font-medium">Original upload</h2>
        <label className="mb-2 block text-sm">
          Stale seeded label (hostile case, optional)
          <input
            data-testid="stale-seeded-label"
            className="mt-1 w-full rounded border p-2"
            value={staleSeededLabel}
            onChange={(e) => setStaleSeededLabel(e.target.value)}
            placeholder="legacy-graph-evidence-v1"
          />
        </label>
        <input
          data-testid="replacement-upload"
          type="file"
          accept=".png,.pdf,.txt"
          onChange={onUpload}
          className="mb-2"
        />
        {sourceId && (
          <p data-testid="source-id" className="text-sm text-gray-600">
            Source: {sourceId}
          </p>
        )}
        {sourceMeta && (
          <>
            <p data-testid="original-sha256" className="text-sm text-gray-600">
              Original SHA-256: {sourceMeta.originalSha256}
            </p>
            <p data-testid="stale-seeded-flag" className="text-sm text-gray-600">
              Stale seeded present: {sourceMeta.hasStaleSeeded ? 'yes' : 'no'}
            </p>
          </>
        )}
        {sourceId && (
          <a
            data-testid="original-viewer-link"
            className="text-blue-700 underline"
            href={`/consultant/replacement/originals/${sourceId}/1`}
            target="_blank"
            rel="noreferrer"
          >
            Open original viewer
          </a>
        )}
        <div className="mt-2">
          <button
            data-testid="create-journey-btn"
            type="button"
            disabled={busy || !sourceId}
            onClick={onCreateJourney}
            className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
          >
            Create journey
          </button>
        </div>
      </section>

      {journey && (
        <section data-testid="journey-section" className="rounded border p-3">
          <h2 className="mb-2 font-medium">Journey {journey.journeyId}</h2>
          <div className="flex flex-wrap gap-2">
            <button data-testid="advance-reading-btn" type="button" disabled={busy || terminal || currentState !== 'uploading'} onClick={() => advance('advance_reading')} className="rounded border px-2 py-1 text-sm">
              Advance reading
            </button>
            <button data-testid="advance-admission-btn" type="button" disabled={busy || terminal || currentState !== 'awaiting_original_reading'} onClick={() => advance('advance_admission')} className="rounded border px-2 py-1 text-sm">
              Advance admission
            </button>
            <button data-testid="advance-processing-btn" type="button" disabled={busy || terminal || currentState !== 'awaiting_admission'} onClick={() => advance('advance_processing')} className="rounded border px-2 py-1 text-sm">
              Advance processing
            </button>
            <button data-testid="land-draft-btn" type="button" disabled={busy || terminal || !canLandDraft} onClick={() => advance('land_draft')} className="rounded border px-2 py-1 text-sm">
              Land draft
            </button>
            <button data-testid="land-revision-btn" type="button" disabled={busy || terminal || !canLandRevision} onClick={() => advance('land_revision')} className="rounded border px-2 py-1 text-sm">
              Land revision
            </button>
            <button data-testid="invalidate-btn" type="button" disabled={busy || terminal} onClick={invalidate} className="rounded border px-2 py-1 text-sm">
              Invalidate current
            </button>
            <button data-testid="cancel-btn" type="button" disabled={busy || !canCancel} onClick={cancel} className="rounded border border-red-500 px-2 py-1 text-sm text-red-700">
              Cancel
            </button>
          </div>

          <div data-testid="model-panel" className="mt-3 rounded border p-2">
            <h3 className="text-sm font-medium">Current model</h3>
            {journey.model ? (
              <>
                <p data-testid="model-version" className="text-sm">
                  Version: {journey.model.version}
                </p>
                <p data-testid="model-hash" className="text-sm">
                  Content hash: {journey.model.contentHash}
                </p>
                <p data-testid="model-id" className="text-sm">
                  Artifact: {journey.model.modelId}
                </p>
              </>
            ) : (
              <p data-testid="model-absent" className="text-sm text-gray-500">
                No current model
              </p>
            )}
          </div>

          <div data-testid="map-panel" className="mt-3 rounded border p-2">
            <h3 className="text-sm font-medium">Map view</h3>
            {journey.mapView ? (
              <>
                <p data-testid="map-workflow" className="text-sm">
                  Workflow: {journey.mapView.workflow.workflow_id}
                </p>
                <ul data-testid="map-steps" className="mt-1 space-y-1">
                  {journey.mapView.workflow.steps.map((step) => (
                    <li key={step.step_id} data-testid={`map-step-${step.step_id}`} className="text-sm">
                      {step.label}
                    </li>
                  ))}
                </ul>
                <ul data-testid="map-transitions" className="mt-1 space-y-1">
                  {journey.mapView.workflow.transitions.map((t) => (
                    <li key={t.transition_id} data-testid={`map-transition-${t.transition_id}`} className="text-sm">
                      {t.from_id} → {t.to_id}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p data-testid="map-absent" className="text-sm text-gray-500">
                No current map
              </p>
            )}
          </div>

          <div data-testid="badge-panel" className="mt-3 rounded border p-2">
            <h3 className="text-sm font-medium">Confirmation badge</h3>
            {journey.confirmation?.current ? (
              <p data-testid="confirmed-badge" className="text-sm text-green-700">
                Reviewed for this scope/version (v{journey.confirmation.version})
              </p>
            ) : (
              <p data-testid="badge-absent" className="text-sm text-gray-500">
                Not confirmed for current scope
              </p>
            )}
            <div className="mt-2 flex gap-2">
              <button data-testid="confirm-btn" type="button" disabled={busy || terminal || !canConfirm} onClick={confirmScope} className="rounded bg-green-600 px-2 py-1 text-sm text-white">
                Confirm exact scope
              </button>
              <button data-testid="withdraw-btn" type="button" disabled={busy || terminal} onClick={withdraw} className="rounded border px-2 py-1 text-sm">
                Withdraw confirmation
              </button>
            </div>
          </div>

          <div data-testid="correction-panel" className="mt-3 rounded border p-2">
            <h3 className="text-sm font-medium">Connection correction (no body edit)</h3>
            <p className="text-xs text-gray-600">
              Correction is append-only original review evidence → new model revision.
            </p>
            <label className="mt-1 block text-sm">
              Reason
              <input
                data-testid="correction-reason"
                className="mt-1 w-full rounded border p-2"
                value={correctionReason}
                onChange={(e) => setCorrectionReason(e.target.value)}
              />
            </label>
            <button data-testid="correct-btn" type="button" disabled={busy || terminal || !canCorrect} onClick={correct} className="mt-2 rounded bg-amber-600 px-2 py-1 text-sm text-white">
              Request connection correction
            </button>
            {journey.corrections && journey.corrections.length > 0 && (
              <ul data-testid="correction-list" className="mt-2 space-y-1">
                {journey.corrections.map((c) => (
                  <li key={c.correctionId} data-testid={`correction-${c.correctionId}`} className="rounded bg-amber-50 p-2 text-sm">
                    <span data-testid="correction-revision">
                      base v{c.baseVersion} → new v{c.resultingModelVersion}
                    </span>
                    <span className="ml-2">original sha {c.originalCorrectionSha256.slice(0, 12)}…</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div data-testid="answer-panel" className="mt-3 rounded border p-2">
            <h3 className="text-sm font-medium">Connected answer</h3>
            <button data-testid="ask-btn" type="button" disabled={busy || terminal || !canAsk} onClick={ask} className="rounded bg-blue-600 px-2 py-1 text-sm text-white">
              Ask supported question
            </button>
            {journey.answer ? (
              <>
                <div data-testid="answer-text" className="mt-2 whitespace-pre-wrap rounded border p-2 text-sm">
                  {journey.answer.text}
                </div>
                <ul data-testid="answer-citations" className="mt-2 space-y-1">
                  {journey.answer.citations.map((c, i) => (
                    <li key={i} data-testid={`citation-${i}`} className="rounded bg-gray-50 p-2 text-sm">
                      {c.quote}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p data-testid="answer-absent" className="mt-2 text-sm text-gray-500">
                No current answer
              </p>
            )}
          </div>

          <div data-testid="attempts-panel" className="mt-3 rounded border p-2">
            <h3 className="text-sm font-medium">Native attempts (never replay)</h3>
            <div className="flex gap-2">
              <button data-testid="dispatch-attempt-btn" type="button" disabled={busy} onClick={() => attemptOp('dispatch')} className="rounded border px-2 py-1 text-sm">
                Dispatch new attempt
              </button>
            </div>
            <ul data-testid="attempt-list" className="mt-2 space-y-1">
              {(journey.attempts ?? []).map((a) => (
                <li key={a.attemptId} data-testid={`attempt-${a.attemptId}`} className="rounded border p-2 text-sm">
                  <span data-testid={`attempt-${a.attemptId}-status`}>{a.attemptId}: {a.status}</span>
                  <span className="ml-2 text-xs text-gray-600">{a.note}</span>
                  {a.status === 'new' && (
                    <button
                      type="button"
                      data-testid={`spend-${a.attemptId}`}
                      disabled={busy}
                      onClick={() => attemptOp('spend', a.attemptId)}
                      className="ml-2 rounded border px-2 py-0.5 text-xs"
                    >
                      Mark spent
                    </button>
                  )}
                  <button
                    type="button"
                    data-testid={`replay-${a.attemptId}`}
                    disabled={busy}
                    onClick={() => attemptOp('replay', a.attemptId)}
                    className="ml-2 rounded border px-2 py-0.5 text-xs"
                  >
                    Replay (must refuse)
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {sourceId && (
            <div data-testid="native-pipeline-panel" className="mt-3 rounded border p-2">
              <h3 className="text-sm font-medium">Native pipeline identity</h3>
              <p data-testid="native-pipeline-output" className="text-sm">
                Current pipeline: native-fixture-v1 bound to original {sourceMeta?.originalSha256?.slice(0, 12) ?? '…'}
              </p>
              {sourceMeta?.hasStaleSeeded && (
                <p data-testid="stale-seeded" className="mt-1 text-xs text-gray-500">
                  Historical seeded metadata present — never current serving output.
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
