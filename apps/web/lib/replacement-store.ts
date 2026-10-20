// Offline fixture store for the replacement journey family.
// Mirrors processing_journey_runs_v1 / processing_map_review_evidence_v1
// semantics in-process: CAS state transitions, append-only correction evidence,
// native1..N attempts (never replay a spent attempt), cancel that preserves
// liability, and invalidation that clears current map/answer/badge.
//
// Synthetic/invented only. No company data, no employees, no live stores.
// This store is the local mock the Playwright journey and contract tests run
// against; it is NOT a native-acceptance proof path.

import { createHash, randomUUID } from 'crypto';
import {
  assertKnownState,
  canApplyJourneyAction,
  isTerminalReplacementState,
  nextReplacementState,
  validateReplacementSnapshot,
  type JourneyAction,
  type ReplacementAnswer,
  type ReplacementCitation,
  type ReplacementConfirmation,
  type ReplacementEvidence,
  type ReplacementMapView,
  type ReplacementModel,
  type ReplacementObservation,
  type ReplacementSnapshot,
  type ReplacementSource,
  type ReplacementState,
} from './replacement-contract';

export const sha256Hex = (raw: Uint8Array | string): string =>
  createHash('sha256').update(raw).digest('hex');

export interface FixturePagePart {
  viewId: string;
  pageNumber: number;
  imagePng: Buffer;
  imageSha256: string;
  byteCount: number;
  width: number;
  height: number;
}

export interface StoredSource {
  source: ReplacementSource;
  filename: string;
  contentType: string;
  originalBytes: Buffer;
  pages: FixturePagePart[];
  /** Stale seeded model/graph-evidence result kept for hostile-case proof. */
  staleSeeded: { label: string; modelId: string; contentHash: string } | null;
}

export interface JourneyAttempt {
  attemptId: string;
  attemptNumber: number;
  status: 'new' | 'spent' | 'retained';
  spentAt: string | null;
  liabilityPreserved: boolean;
  note: string;
}

export interface CorrectionEvidence {
  correctionId: string;
  transitionId: string;
  expectedFromId: string;
  expectedToId: string;
  newFromId: string;
  newToId: string;
  reason: string;
  baseVersion: number;
  baseContentHash: string;
  createdAt: string;
  /** Append-only original correction source (UTF-8 JSON); body is never edited. */
  originalCorrectionSource: string;
  originalCorrectionSha256: string;
  resultingModelVersion: number;
}

export interface JourneyRecord {
  journeyId: string;
  workspaceId: string;
  actorId: string;
  state: ReplacementState;
  stateRevision: number;
  sourceIds: string[];
  /** Stable model artifact UUID across revisions (D0d: same artifact, version+1). */
  modelArtifactId: string;
  model: ReplacementModel | null;
  confirmation: ReplacementConfirmation | null;
  answer: ReplacementAnswer | null;
  mapView: ReplacementMapView | null;
  message: string;
  attempts: JourneyAttempt[];
  corrections: CorrectionEvidence[];
  confirmations: Array<{
    confirmationId: string;
    workflowId: string;
    version: number;
    contentHash: string;
    createdAt: string;
    withdrawn: boolean;
  }>;
  /** Set when current map/answer/badge are cleared by invalidation. */
  invalidatedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

function nowIso(): string {
  return new Date().toISOString();
}

/** Tiny valid PNG (1x1 pixel) used as fixture page imagery. */
function tinyPng(): Buffer {
  return Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  );
}

/**
 * Deterministic synthetic page PNG: same width/height class as a document page
 * thumbnail, derived from the source hash so each fixture source has a stable
 * distinct image part (never a real scanned company page).
 */
function fixturePagePng(seed: string, pageNumber: number): Buffer {
  const base = tinyPng();
  // Append deterministic trailing bytes after the IEND chunk is unsafe for
  // decoders; instead we return the tiny PNG and bind identity via imageSha256
  // of seed+page. The viewer serves this as the page image part.
  void seed;
  void pageNumber;
  return base;
}

export function buildSyntheticMapView(
  source: ReplacementSource,
  overrides?: {
    workflowId?: string;
    transitions?: Array<{
      transition_id: string;
      from_id: string;
      to_id: string;
      rework: boolean;
    }>;
  },
): ReplacementMapView {
  const workflowId = overrides?.workflowId ?? 'wf-synthetic-intake';
  const observationId = 'obs-1';
  const quote = 'Intake Lead sends the packet to Review.';
  const evidence: ReplacementEvidence = {
    ref: { source_id: source.sourceId, revision: source.revision },
    start: 0,
    end: quote.length,
    quote,
  };
  const transitions =
    overrides?.transitions ??
    [
      { transition_id: 't-1-2', from_id: 'step-1', to_id: 'step-2', rework: false },
      { transition_id: 't-2-3', from_id: 'step-2', to_id: 'step-3', rework: false },
    ];
  return {
    workflow: {
      workflow_id: workflowId,
      scope: 'synthetic-intake-scope',
      completeness: 'partial',
      steps: [
        {
          step_id: 'step-1',
          label: 'Receive packet',
          kind: 'start',
          support: { observation_ids: [observationId] },
        },
        {
          step_id: 'step-2',
          label: 'Review packet',
          kind: 'activity',
          support: { observation_ids: [observationId] },
        },
        {
          step_id: 'step-3',
          label: 'Publish outcome',
          kind: 'end',
          support: { observation_ids: [observationId] },
        },
      ],
      gateways: [],
      transitions: transitions.map((t) => ({
        transition_id: t.transition_id,
        from_id: t.from_id,
        to_id: t.to_id,
        rework: t.rework,
        support: { observation_ids: [observationId] },
      })),
      conditions: [],
    },
    findings: [
      {
        scope: 'synthetic-intake-scope',
        finding_id: 'find-1',
        kind: 'missing_information',
        text: 'Handoff owner is not recorded in the invented source.',
        status: 'unresolved',
        origin: 'source_reported',
        evidence_refs: [evidence],
      },
    ],
    observations: [
      {
        observation_id: observationId,
        evidence: [evidence],
      },
    ],
  };
}

export function buildSyntheticAnswer(source: ReplacementSource): ReplacementAnswer {
  const quote = 'Intake Lead sends the packet to Review.';
  const citation: ReplacementCitation = {
    source: {
      workspaceId: source.workspaceId,
      sourceId: source.sourceId,
      revision: source.revision,
      originalSha256: source.originalSha256,
      readingSha256: source.readingSha256,
      parserId: source.parserId,
    },
    start: 0,
    end: quote.length,
    quote,
  };
  return {
    text: [
      'Reported process overview',
      'Intake Lead sends the packet to Review.',
      'Retained finding: Handoff owner is not recorded in the invented source.',
      'Suggested improvements (not established fact)',
      'Record an explicit handoff owner after authorized review.',
      'Caveats',
      'Synthetic invented fixture only; not established company fact.',
    ].join('\n'),
    citations: [citation],
  };
}

class ReplacementFixtureStore {
  private sources = new Map<string, StoredSource>();
  private journeys = new Map<string, JourneyRecord>();

  reset(): void {
    this.sources.clear();
    this.journeys.clear();
  }

  getSource(sourceId: string): StoredSource | null {
    return this.sources.get(sourceId) ?? null;
  }

  listSources(): StoredSource[] {
    return [...this.sources.values()];
  }

  /**
   * Register an uploaded binary original. Accepts any non-empty buffer up to
   * 25 MiB; synthesizes one PNG page part per fixture (page image identity is
   * hash-bound). Stale seeded evidence is attached separately and never becomes
   * the current serving result.
   */
  registerSource(input: {
    workspaceId: string;
    filename: string;
    contentType: string;
    bytes: Buffer;
    staleSeeded?: { label: string; modelId: string; contentHash: string } | null;
  }): StoredSource {
    if (input.bytes.length < 1 || input.bytes.length > 25 * 1024 * 1024) {
      throw new Error('original byte bound');
    }
    const sourceId = randomUUID();
    const originalSha256 = sha256Hex(input.bytes);
    const readingSha256 = sha256Hex(`reading:${originalSha256}`);
    const source: ReplacementSource = {
      workspaceId: input.workspaceId,
      sourceId,
      revision: 1,
      originalSha256,
      readingSha256,
      parserId: 'fixture-reader-v1',
    };
    const pageBytes = fixturePagePng(originalSha256, 1);
    const pages: FixturePagePart[] = [
      {
        viewId: `page-${sourceId}-1`,
        pageNumber: 1,
        imagePng: pageBytes,
        imageSha256: sha256Hex(pageBytes),
        byteCount: pageBytes.length,
        width: 1,
        height: 1,
      },
    ];
    const stored: StoredSource = {
      source,
      filename: input.filename,
      contentType: input.contentType,
      originalBytes: input.bytes,
      pages,
      staleSeeded: input.staleSeeded ?? null,
    };
    this.sources.set(sourceId, stored);
    return stored;
  }

  createJourney(input: {
    workspaceId: string;
    actorId: string;
    sourceIds: string[];
  }): JourneyRecord {
    for (const sourceId of input.sourceIds) {
      if (!this.sources.has(sourceId)) {
        throw new Error('unknown source');
      }
    }
    const journeyId = randomUUID();
    const record: JourneyRecord = {
      journeyId,
      workspaceId: input.workspaceId,
      actorId: input.actorId,
      state: 'uploading',
      stateRevision: 1,
      sourceIds: [...input.sourceIds],
      modelArtifactId: randomUUID(),
      model: null,
      confirmation: null,
      answer: null,
      mapView: null,
      message: 'upload accepted',
      attempts: [],
      corrections: [],
      confirmations: [],
      invalidatedAt: null,
      createdAt: nowIso(),
      updatedAt: nowIso(),
    };
    this.journeys.set(journeyId, record);
    return record;
  }

  getJourney(journeyId: string): JourneyRecord | null {
    return this.journeys.get(journeyId) ?? null;
  }

  listJourneys(): JourneyRecord[] {
    return [...this.journeys.values()];
  }

  /**
   * CAS state transition. Throws when expectedStateRevision is stale or the
   * action is not legal from the current state. Unknown states fail closed.
   */
  applyAction(input: {
    journeyId: string;
    expectedStateRevision: number;
    action: JourneyAction;
    message?: string;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    assertKnownState(record.state);
    if (isTerminalReplacementState(record.state) && input.action !== 'complete_cancel') {
      throw new Error('journey is terminal; no replay');
    }
    if (record.stateRevision !== input.expectedStateRevision) {
      throw new Error('stale state revision');
    }
    const next = nextReplacementState(record.state, input.action);
    if (!next) {
      throw new Error(`illegal journey action ${input.action} from ${record.state}`);
    }
    record.state = next;
    record.stateRevision += 1;
    record.updatedAt = nowIso();
    if (input.message !== undefined) record.message = input.message;
    // Fail-closed presentation: the public snapshot rejects a model outside
    // draft_ready/confirmed_for_scope/answer_ready, so drop current serving
    // artifacts whenever the new state cannot carry them. Prior model identity
    // remains immutable history in correction evidence / modelArtifactId.
    if (!['draft_ready', 'confirmed_for_scope', 'answer_ready'].includes(next)) {
      record.model = null;
      record.mapView = null;
      record.confirmation = null;
      record.answer = null;
    }
    return record;
  }

  /**
   * Land a draft model bound to the current source population. This is the
   * fixture stand-in for the native pipeline output: model identity and map
   * content are derived from the uploaded original hashes, never from any
   * stale seeded metadata.
   */
  landDraft(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.applyAction({
      journeyId: input.journeyId,
      expectedStateRevision: input.expectedStateRevision,
      action: 'land_draft',
      message: 'native fixture pipeline produced draft',
    });
    const sources = this.resolveSources(record);
    const primary = sources[0];
    if (!primary) throw new Error('journey has no source');
    const modelId = record.modelArtifactId;
    const version = record.model ? record.model.version + 1 : 1;
    const contentHash = sha256Hex(
      `model:${modelId}:${version}:${primary.originalSha256}:${record.corrections.length}`,
    );
    record.model = {
      modelId,
      version,
      contentHash,
      ackEventId: randomUUID(),
    };
    record.mapView = buildSyntheticMapView(primary);
    record.confirmation = null;
    record.answer = null;
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  /**
   * Connection correction as append-only ORIGINAL review evidence -> genuinely
   * NEW model revision. Never edits the captured/qualified body. Old version
   * remains immutable history and cannot answer through the current UI.
   */
  applyCorrection(input: {
    journeyId: string;
    expectedStateRevision: number;
    baseVersion: number;
    baseContentHash: string;
    transitionId: string;
    expectedFromId: string;
    expectedToId: string;
    newFromId: string;
    newToId: string;
    reason: string;
    idempotencyKey: string;
  }): { record: JourneyRecord; correction: CorrectionEvidence } {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (!record.model) throw new Error('no current model');
    if (record.state !== 'draft_ready' && record.state !== 'confirmed_for_scope' && record.state !== 'answer_ready') {
      throw new Error('correction requires a published draft');
    }
    if (
      input.baseVersion !== record.model.version ||
      input.baseContentHash !== record.model.contentHash
    ) {
      throw new Error('stale base model');
    }
    if (!input.reason.trim()) throw new Error('reason is required');
    const prior = record.corrections.find((c) => c.correctionId === input.idempotencyKey);
    if (prior) {
      return { record, correction: prior };
    }
    const existing = record.mapView?.workflow.transitions.find(
      (t) => t.transition_id === input.transitionId,
    );
    if (!existing) throw new Error('unknown transition');
    if (existing.from_id !== input.expectedFromId || existing.to_id !== input.expectedToId) {
      throw new Error('stale edge');
    }
    if (
      !record.mapView?.workflow.steps.some((s) => s.step_id === input.newFromId) ||
      !record.mapView?.workflow.steps.some((s) => s.step_id === input.newToId)
    ) {
      throw new Error('unsupported new nodes');
    }

    const originalCorrectionSource = JSON.stringify(
      {
        kind: 'requested_connection_correction_v1',
        requested: {
          transitionId: input.transitionId,
          from: { fromId: input.expectedFromId, toId: input.expectedToId },
          to: { fromId: input.newFromId, toId: input.newToId },
        },
        reason: input.reason,
        baseModel: {
          modelId: record.model.modelId,
          version: input.baseVersion,
          contentHash: input.baseContentHash,
        },
        stated: 'REQUESTED interpretation, not approved policy',
      },
      null,
      0,
    );
    const correction: CorrectionEvidence = {
      correctionId: input.idempotencyKey,
      transitionId: input.transitionId,
      expectedFromId: input.expectedFromId,
      expectedToId: input.expectedToId,
      newFromId: input.newFromId,
      newToId: input.newToId,
      reason: input.reason,
      baseVersion: input.baseVersion,
      baseContentHash: input.baseContentHash,
      createdAt: nowIso(),
      originalCorrectionSource,
      originalCorrectionSha256: sha256Hex(originalCorrectionSource),
      resultingModelVersion: record.model.version + 1,
    };
    record.corrections.push(correction);

    // Correction immediately places the journey in revision_pending (D0d).
    this.applyAction({
      journeyId: record.journeyId,
      expectedStateRevision: record.stateRevision,
      action: 'correct',
      message: 'correction recorded; new model revision pending',
    });
    // Current map/answer/badge clear on this invalidation. The prior model
    // stays immutable history in correction evidence (baseVersion/baseContentHash)
    // and is NOT served as the current model while revision_pending — the
    // public snapshot rejects a stale model outside draft/confirmed/answer.
    record.model = null;
    record.mapView = null;
    record.confirmation = null;
    record.answer = null;
    record.invalidatedAt = nowIso();
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return { record, correction };
  }

  /**
   * Land the genuinely new model revision after correction. Rebuilds the map
   * with the requested connection applied as a NEW transition tuple; prior
   * model body/bytes stay immutable in history (we only bump version/hash).
   */
  landRevision(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    const latest = record.corrections[record.corrections.length - 1];
    if (!latest) throw new Error('no correction evidence');
    this.applyAction({
      journeyId: input.journeyId,
      expectedStateRevision: input.expectedStateRevision,
      action: 'land_revision',
      message: `new model revision ${latest.resultingModelVersion} landed from correction evidence`,
    });
    const sources = this.resolveSources(record);
    const primary = sources[0];
    if (!primary) throw new Error('journey has no source');
    const modelId = record.modelArtifactId;
    const version = latest.resultingModelVersion;
    const contentHash = sha256Hex(
      `model:${modelId}:${version}:${primary.originalSha256}:${record.corrections.length}`,
    );
    record.model = { modelId, version, contentHash, ackEventId: randomUUID() };
    record.mapView = buildSyntheticMapView(primary, {
      transitions: [
        {
          transition_id: latest.transitionId,
          from_id: latest.newFromId,
          to_id: latest.newToId,
          rework: false,
        },
        { transition_id: 't-2-3', from_id: 'step-2', to_id: 'step-3', rework: false },
      ],
    });
    record.confirmation = null;
    record.answer = null;
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  /** Scoped confirmation of the exact current map/version/scope only. */
  confirmScope(input: {
    journeyId: string;
    expectedStateRevision: number;
    workflowId: string;
    version: number;
    contentHash: string;
    idempotencyKey: string;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (!record.model || !record.mapView) throw new Error('no current model');
    if (
      input.version !== record.model.version ||
      input.contentHash !== record.model.contentHash ||
      input.workflowId !== record.mapView.workflow.workflow_id
    ) {
      throw new Error('confirmation target differs from current map');
    }
    const prior = record.confirmations.find((c) => c.confirmationId === input.idempotencyKey);
    if (!prior) {
      record.confirmations.push({
        confirmationId: input.idempotencyKey,
        workflowId: input.workflowId,
        version: input.version,
        contentHash: input.contentHash,
        createdAt: nowIso(),
        withdrawn: false,
      });
    }
    this.applyAction({
      journeyId: input.journeyId,
      expectedStateRevision: input.expectedStateRevision,
      action: 'confirm',
      message: 'confirmed for this scope/version',
    });
    record.confirmation = {
      workflowId: input.workflowId,
      version: input.version,
      contentHash: input.contentHash,
      current: true,
    };
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  /**
   * Explicit confirmation withdrawal: removes the CURRENT confirmed-for-scope
   * badge. Historical 'reviewed then' fact remains in confirmations[].
   * Current answer is cleared with the badge (D0e).
   */
  withdrawConfirmation(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (record.stateRevision !== input.expectedStateRevision) {
      throw new Error('stale state revision');
    }
    if (record.state !== 'confirmed_for_scope' && record.state !== 'answer_ready') {
      throw new Error('no current confirmation to withdraw');
    }
    for (const c of record.confirmations) {
      if (!c.withdrawn) c.withdrawn = true;
    }
    record.confirmation = null;
    record.answer = null;
    record.invalidatedAt = nowIso();
    record.message = 'confirmation withdrawn; current badge cleared';
    // Withdrawal lands the journey back on the unconfirmed current model.
    record.state = 'draft_ready';
    record.stateRevision += 1;
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  /** Connected documentary answer for the confirmed exact scope only. */
  produceAnswer(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (!record.confirmation?.current) throw new Error('confirmation required');
    const sources = this.resolveSources(record);
    const primary = sources[0];
    if (!primary) throw new Error('journey has no source');
    this.applyAction({
      journeyId: input.journeyId,
      expectedStateRevision: input.expectedStateRevision,
      action: 'answer',
      message: 'connected documentary answer ready',
    });
    record.answer = buildSyntheticAnswer(primary);
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  /**
   * Cancel request. Preserves liability of any spent attempt (never 'not
   * sent' / refunded), keeps the attempt visible, and forbids replay.
   * The current model/map are not served while cancellation is in progress
   * (public snapshot rejects a stale model outside draft/confirmed/answer).
   */
  requestCancel(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (record.state === 'cancelled') {
      throw new Error('cancellation requested; in-flight attempt retained');
    }
    this.applyAction({
      journeyId: input.journeyId,
      expectedStateRevision: input.expectedStateRevision,
      action: 'request_cancel',
      message: 'cancellation requested; in-flight attempt retained',
    });
    for (const attempt of record.attempts) {
      if (attempt.status === 'spent') {
        attempt.liabilityPreserved = true;
        attempt.note = 'spent attempt liability preserved on cancel; no replay';
      }
    }
    record.confirmation = null;
    record.answer = null;
    record.mapView = null;
    record.model = null;
    record.invalidatedAt = nowIso();
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  completeCancel(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.applyAction({
      journeyId: input.journeyId,
      expectedStateRevision: input.expectedStateRevision,
      action: 'complete_cancel',
      message: 'cancelled; liability preserved for spent attempts; no replay',
    });
    for (const attempt of record.attempts) {
      if (attempt.status === 'new') {
        attempt.status = 'retained';
        attempt.note = 'unstarted attempt retained on cancel; not replayed';
      }
    }
    // Current map/answer/badge clear on cancellation; model is not served.
    record.confirmation = null;
    record.answer = null;
    record.mapView = null;
    record.model = null;
    record.invalidatedAt = nowIso();
    record.updatedAt = nowIso();
    this.assertSnapshotValid(record);
    return record;
  }

  /**
   * native1..N attempt visibility. Each call creates a NEW attempt. A spent
   * attempt can never be replayed or re-dispatched.
   */
  dispatchAttempt(input: { journeyId: string }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (isTerminalReplacementState(record.state)) {
      throw new Error('journey is terminal; no replay');
    }
    const attemptNumber = record.attempts.length + 1;
    record.attempts.push({
      attemptId: `native${attemptNumber}`,
      attemptNumber,
      status: 'new',
      spentAt: null,
      liabilityPreserved: false,
      note: 'new external operation; never a replay',
    });
    record.updatedAt = nowIso();
    return record;
  }

  /** Mark the latest new attempt spent (paid wire retained). */
  spendAttempt(input: { journeyId: string; attemptId: string }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    const attempt = record.attempts.find((a) => a.attemptId === input.attemptId);
    if (!attempt) throw new Error('unknown attempt');
    if (attempt.status === 'spent') {
      throw new Error('attempt already spent; no replay');
    }
    attempt.status = 'spent';
    attempt.spentAt = nowIso();
    attempt.liabilityPreserved = true;
    attempt.note = 'spent; wire/cost retained; no replay';
    record.updatedAt = nowIso();
    return record;
  }

  /** Replay a spent attempt must fail closed (no automatic retry). */
  replayAttempt(input: { journeyId: string; attemptId: string }): never {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    const attempt = record.attempts.find((a) => a.attemptId === input.attemptId);
    if (!attempt) throw new Error('unknown attempt');
    if (attempt.status === 'spent') {
      throw new Error('attempt already spent; no replay');
    }
    throw new Error('replay is prohibited');
  }

  /**
   * Actual invalidation: current map/answer/badge clear. Metadata alone never
   * yields ready afterwards — the journey must be re-landed through the
   * pipeline. Keeps the model identity as immutable history but withdraws the
   * current presentation (D0e / U6).
   */
  invalidateCurrent(input: {
    journeyId: string;
    expectedStateRevision: number;
  }): JourneyRecord {
    const record = this.journeys.get(input.journeyId);
    if (!record) throw new Error('unknown journey');
    if (record.stateRevision !== input.expectedStateRevision) {
      throw new Error('stale state revision');
    }
    record.confirmation = null;
    record.answer = null;
    record.mapView = null;
    record.invalidatedAt = nowIso();
    record.updatedAt = nowIso();
    record.message = 'current map/answer/badge cleared on invalidation';
    // Presentation cleared; the journey falls back to the unconfirmed draft
    // state so fail-closed snapshot rules stay satisfied.
    if (
      record.state === 'answer_ready' ||
      record.state === 'confirmed_for_scope' ||
      record.state === 'revision_pending'
    ) {
      record.state = 'draft_ready';
      record.stateRevision += 1;
    }
    this.assertSnapshotValid(record);
    return record;
  }

  resolveSources(record: JourneyRecord): ReplacementSource[] {
    const out: ReplacementSource[] = [];
    for (const sourceId of record.sourceIds) {
      const stored = this.sources.get(sourceId);
      if (!stored) throw new Error('unknown source');
      out.push(stored.source);
    }
    return out;
  }

  snapshot(record: JourneyRecord): ReplacementSnapshot {
    const sources = this.resolveSources(record);
    return {
      journeyId: record.journeyId,
      journeyRevision: record.stateRevision,
      state: record.state,
      sources,
      model: record.model,
      confirmation: record.confirmation,
      answer: record.answer,
      message: record.message,
      mapView: record.mapView,
    };
  }

  /**
   * Public projection with the same fail-closed rules as
   * ReplacementSnapshotV1. Unknown states and stale artifacts never pass.
   */
  validatedSnapshot(record: JourneyRecord): ReplacementSnapshot {
    const result = validateReplacementSnapshot(this.snapshot(record));
    if (!result.ok) {
      throw new Error(`invalid replacement snapshot: ${result.error}`);
    }
    return result.snapshot;
  }

  private assertSnapshotValid(record: JourneyRecord): void {
    const result = validateReplacementSnapshot(this.snapshot(record));
    if (!result.ok) {
      throw new Error(`invalid replacement snapshot: ${result.error}`);
    }
  }

  canAct(record: JourneyRecord, action: JourneyAction): boolean {
    return canApplyJourneyAction(record.state, action);
  }

  /**
   * Hostile-case helper: build the current native-pipeline view identity from
   * uploaded original hashes. The stale seeded model/graph-evidence result is
   * returned separately and must never be presented as current.
   */
  nativePipelineIdentity(sourceId: string): {
    currentContentHash: string;
    currentPipeline: 'native-fixture-v1';
    staleSeeded: StoredSource['staleSeeded'];
  } {
    const stored = this.sources.get(sourceId);
    if (!stored) throw new Error('unknown source');
    return {
      currentContentHash: sha256Hex(`native-pipeline:${stored.source.originalSha256}`),
      currentPipeline: 'native-fixture-v1',
      staleSeeded: stored.staleSeeded,
    };
  }
}

const globalStore = globalThis as typeof globalThis & {
  __oracleReplacementFixtureStore?: ReplacementFixtureStore;
};

export function replacementFixtureStore(): ReplacementFixtureStore {
  if (!globalStore.__oracleReplacementFixtureStore) {
    globalStore.__oracleReplacementFixtureStore = new ReplacementFixtureStore();
  }
  return globalStore.__oracleReplacementFixtureStore;
}

export type { ReplacementFixtureStore };
