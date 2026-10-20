// Replacement journey wire contract (TypeScript mirror of
// services/oracle-brain/oracle_brain/hosting/replacement_public_view_v1.py and
// replacement_result_v1.py). Fail-closed on unknown states; never invent
// 'ready' from metadata alone. Synthetic/invented data only.

export const REPLACEMENT_PROTOCOL = 'replacement-protected-result-v1' as const;

export const REPLACEMENT_STATES = [
  'uploading',
  'awaiting_original_reading',
  'awaiting_admission',
  'processing',
  'draft_ready',
  'revision_pending',
  'confirmed_for_scope',
  'answer_ready',
  'cancel_requested',
  'cancelled',
  'failed_spent',
  'error',
  'evidence_missing',
] as const;

export type ReplacementState = (typeof REPLACEMENT_STATES)[number];

export function isReplacementState(value: unknown): value is ReplacementState {
  return (
    typeof value === 'string' &&
    (REPLACEMENT_STATES as readonly string[]).includes(value)
  );
}

const HASH_RE = /^[a-f0-9]{64}$/;
const ID_RE =
  /^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000|[fF]{8}-[fF]{4}-[fF]{4}-[fF]{4}-[fF]{12})$/;

function isHash(value: unknown): value is string {
  return typeof value === 'string' && HASH_RE.test(value);
}

function isId(value: unknown): value is string {
  return typeof value === 'string' && ID_RE.test(value);
}

function isName(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= 200;
}

function isRevision(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 9007199254740991;
}

/**
 * Promotion to confirmed/answer-ready requires bound qualification/review
 * commits on every source. Intake-only callers and commit-less sources never
 * promote (mirrors SQL/Python delivered gates).
 */
export function promotionEvidenceBound(
  sources: readonly { readerCommit?: string; reviewerCommit?: string }[],
): boolean {
  return (
    sources.length > 0 &&
    sources.every((s) => isHash(s.readerCommit) && isHash(s.reviewerCommit))
  );
}

export interface ReplacementSource {
  workspaceId: string;
  sourceId: string;
  revision: number;
  originalSha256: string;
  readingSha256: string;
  parserId: string;
  /** Qualification commit seal; required to promote to confirmed/answer-ready. */
  readerCommit?: string;
  /** Review commit seal; required to promote to confirmed/answer-ready. */
  reviewerCommit?: string;
}

export interface EvidenceSourceRef {
  source_id: string;
  revision: number;
}

export interface ReplacementSpan {
  start: number;
  end: number;
  quote: string;
}

export interface ReplacementEvidence extends ReplacementSpan {
  ref: EvidenceSourceRef;
}

export interface ReplacementCitation extends ReplacementSpan {
  source: ReplacementSource;
  pageView?: ReplacementPageView;
}

export interface ReplacementPageView {
  viewId: string;
  pageNumber: number;
  imageSha256: string;
  byteCount: number;
  width: number;
  height: number;
}

export interface ReplacementModel {
  modelId: string;
  version: number;
  contentHash: string;
  ackEventId: string;
}

export interface ReplacementConfirmation {
  workflowId: string;
  version: number;
  contentHash: string;
  current: boolean;
}

export interface ReplacementAnswer {
  text: string;
  citations: ReplacementCitation[];
}

export interface ReplacementSupport {
  observation_ids: string[];
}

export type ReplacementStepKind =
  | 'activity'
  | 'start'
  | 'end'
  | 'rejection'
  | 'call'
  | 'return';

export interface ReplacementStep {
  step_id: string;
  label: string;
  kind: ReplacementStepKind;
  role_id?: string;
  support: ReplacementSupport;
}

export interface ReplacementGateway {
  gateway_id: string;
  kind: 'exclusive_split' | 'exclusive_join' | 'parallel_split' | 'parallel_join' | 'unsupported';
  support: ReplacementSupport;
}

export interface ReplacementTransition {
  transition_id: string;
  from_id: string;
  to_id: string;
  condition_id?: string;
  rework: boolean;
  support: ReplacementSupport;
}

export interface ReplacementCondition {
  condition_id: string;
  wording: string;
  applicability: string;
}

export interface ReplacementWorkflow {
  workflow_id: string;
  scope: string;
  completeness: 'partial' | 'complete' | 'ambiguous' | 'conflicted';
  steps: ReplacementStep[];
  gateways: ReplacementGateway[];
  transitions: ReplacementTransition[];
  conditions: ReplacementCondition[];
}

export interface ReplacementFinding {
  scope: string;
  finding_id: string;
  kind: 'missing_information' | 'source_conflict' | 'model_incomplete';
  text: string;
  status: 'unresolved' | 'resolved_by_authorized_review' | 'superseded' | 'withdrawn' | 'needs_evidence';
  origin:
    | 'source_reported'
    | 'reported_conflict_unverified'
    | 'coverage_inference'
    | 'legacy_unverified'
    | 'structural_diagnostic';
  evidence_refs: ReplacementEvidence[];
}

export interface ReplacementObservation {
  observation_id: string;
  evidence: ReplacementEvidence[];
}

export interface ReplacementMapView {
  workflow: ReplacementWorkflow;
  findings: ReplacementFinding[];
  observations: ReplacementObservation[];
}

export interface ReplacementSnapshot {
  journeyId: string;
  journeyRevision: number;
  state: ReplacementState;
  sources: ReplacementSource[];
  model: ReplacementModel | null;
  confirmation: ReplacementConfirmation | null;
  answer: ReplacementAnswer | null;
  message: string;
  mapView: ReplacementMapView | null;
}

export type SnapshotValidationError = string;

function evidenceMatchesSources(
  evidence: ReplacementEvidence,
  sources: ReplacementSource[],
): boolean {
  return sources.some(
    (s) => s.sourceId === evidence.ref.source_id && s.revision === evidence.ref.revision,
  );
}

function validateMapViewLinks(mapView: ReplacementMapView): SnapshotValidationError | null {
  const w = mapView.workflow;
  const nodeIds = [
    ...w.steps.map((s) => s.step_id),
    ...w.gateways.map((g) => g.gateway_id),
  ];
  const allIds = [
    ...nodeIds,
    ...w.transitions.map((t) => t.transition_id),
    ...w.conditions.map((c) => c.condition_id),
  ];
  const observationIds = mapView.observations.map((o) => o.observation_id);
  if (new Set(allIds).size !== allIds.length) return 'duplicate identity';
  if (new Set(observationIds).size !== observationIds.length) return 'duplicate identity';
  const observationSet = new Set(observationIds);
  for (const item of [...w.steps, ...w.gateways, ...w.transitions]) {
    for (const obsId of item.support.observation_ids) {
      if (!observationSet.has(obsId)) return 'missing support';
    }
  }
  const nodeSet = new Set(nodeIds);
  for (const t of w.transitions) {
    if (!nodeSet.has(t.from_id) || !nodeSet.has(t.to_id)) return 'dangling connection';
    if (
      t.condition_id !== undefined &&
      !w.conditions.some((c) => c.condition_id === t.condition_id)
    ) {
      return 'dangling connection';
    }
  }
  return null;
}

/**
 * Mirror of ReplacementSnapshotV1 model_validator(mode='after').current().
 * Fail-closed: any invariant violation rejects the snapshot. Unknown states
 * are rejected before any 'ready' inference.
 */
export function validateReplacementSnapshot(
  value: unknown,
): { ok: true; snapshot: ReplacementSnapshot } | { ok: false; error: SnapshotValidationError } {
  if (typeof value !== 'object' || value === null) {
    return { ok: false, error: 'snapshot object required' };
  }
  const raw = value as Record<string, unknown>;
  if (!isId(raw.journeyId)) return { ok: false, error: 'invalid journeyId' };
  if (!isRevision(raw.journeyRevision)) return { ok: false, error: 'invalid journeyRevision' };
  if (!isReplacementState(raw.state)) {
    return { ok: false, error: 'unknown replacement state' };
  }
  const state = raw.state;
  if (!Array.isArray(raw.sources) || raw.sources.length > 100) {
    return { ok: false, error: 'invalid sources' };
  }
  const sources: ReplacementSource[] = [];
  for (const s of raw.sources) {
    const src = s as Record<string, unknown>;
    if (
      !isId(src.workspaceId) ||
      !isId(src.sourceId) ||
      !isRevision(src.revision) ||
      !isHash(src.originalSha256) ||
      !isHash(src.readingSha256) ||
      !isName(src.parserId) ||
      (src.readerCommit !== undefined && !isHash(src.readerCommit)) ||
      (src.reviewerCommit !== undefined && !isHash(src.reviewerCommit))
    ) {
      return { ok: false, error: 'invalid source' };
    }
    sources.push({
      workspaceId: src.workspaceId,
      sourceId: src.sourceId,
      revision: src.revision,
      originalSha256: src.originalSha256,
      readingSha256: src.readingSha256,
      parserId: src.parserId,
      readerCommit: src.readerCommit,
      reviewerCommit: src.reviewerCommit,
    });
  }
  if (new Set(sources.map((s) => s.sourceId)).size !== sources.length) {
    return { ok: false, error: 'duplicate source' };
  }

  if (
    (state === 'confirmed_for_scope' || state === 'answer_ready') &&
    !promotionEvidenceBound(sources)
  ) {
    return { ok: false, error: 'qualification and review commits required for promotion' };
  }

  const model = raw.model as ReplacementModel | null | undefined;
  const confirmation = raw.confirmation as ReplacementConfirmation | null | undefined;
  const answer = raw.answer as ReplacementAnswer | null | undefined;
  const mapView = raw.mapView as ReplacementMapView | null | undefined;
  const message = typeof raw.message === 'string' ? raw.message : '';

  if (model !== null && model !== undefined) {
    if (
      !isId(model.modelId) ||
      !isRevision(model.version) ||
      !isHash(model.contentHash) ||
      !isId(model.ackEventId)
    ) {
      return { ok: false, error: 'invalid model' };
    }
    if (!['draft_ready', 'confirmed_for_scope', 'answer_ready'].includes(state)) {
      return { ok: false, error: 'stale model' };
    }
  }

  if (mapView !== null && mapView !== undefined) {
    if (!model) return { ok: false, error: 'map requires model' };
    const linkError = validateMapViewLinks(mapView);
    if (linkError) return { ok: false, error: linkError };
    const evidenceList: ReplacementEvidence[] = [
      ...mapView.findings.flatMap((f) => f.evidence_refs),
      ...mapView.observations.flatMap((o) => o.evidence),
    ];
    for (const evidence of evidenceList) {
      if (!evidenceMatchesSources(evidence, sources)) {
        return { ok: false, error: 'foreign evidence' };
      }
    }
    if (
      confirmation &&
      confirmation.current &&
      confirmation.workflowId !== mapView.workflow.workflow_id
    ) {
      return { ok: false, error: 'confirmation differs' };
    }
  }

  if (confirmation !== null && confirmation !== undefined) {
    if (
      !isName(confirmation.workflowId) ||
      !isRevision(confirmation.version) ||
      !isHash(confirmation.contentHash) ||
      typeof confirmation.current !== 'boolean'
    ) {
      return { ok: false, error: 'invalid confirmation' };
    }
    if (confirmation.current) {
      if (
        !model ||
        confirmation.version !== model.version ||
        confirmation.contentHash !== model.contentHash ||
        !['confirmed_for_scope', 'answer_ready'].includes(state)
      ) {
        return { ok: false, error: 'confirmation differs' };
      }
    }
  }

  if (state === 'confirmed_for_scope' && !(confirmation && confirmation.current)) {
    return { ok: false, error: 'confirmation required' };
  }

  if (answer !== null && answer !== undefined) {
    if (typeof answer.text !== 'string' || !Array.isArray(answer.citations)) {
      return { ok: false, error: 'invalid answer' };
    }
    if (state !== 'answer_ready') return { ok: false, error: 'stale answer' };
    if (!model) return { ok: false, error: 'answer required' };
    if (answer.citations.length < 1 || answer.citations.length > 100) {
      return { ok: false, error: 'invalid answer citations' };
    }
    for (const citation of answer.citations) {
      if (
        typeof citation.start !== 'number' ||
        !Number.isInteger(citation.start) ||
        citation.start < 0 ||
        !isRevision(citation.end)
      ) {
        return { ok: false, error: 'invalid citation span' };
      }
      if (citation.end <= citation.start) {
        return { ok: false, error: 'invalid citation span' };
      }
      if (citation.quote.length !== citation.end - citation.start) {
        return { ok: false, error: 'invalid citation quote' };
      }
      const matched = sources.some(
        (s) =>
          s.workspaceId === citation.source.workspaceId &&
          s.sourceId === citation.source.sourceId &&
          s.revision === citation.source.revision,
      );
      if (!matched) return { ok: false, error: 'foreign citation' };
    }
  }

  if (state === 'answer_ready' && !(model && answer)) {
    return { ok: false, error: 'answer required' };
  }

  return {
    ok: true,
    snapshot: {
      journeyId: raw.journeyId,
      journeyRevision: raw.journeyRevision,
      state,
      sources,
      model: model ?? null,
      confirmation: confirmation ?? null,
      answer: answer ?? null,
      message,
      mapView: mapView ?? null,
    },
  };
}

/** Fail-closed: unknown state strings are never coerced into a known state. */
export function assertKnownState(value: unknown): ReplacementState {
  if (!isReplacementState(value)) {
    throw new Error('unknown replacement state');
  }
  return value;
}

// Journey control transitions (CAS-protected). Mirrors D0d publication/CAS:
// correction immediately places the journey in revision_pending; the old
// model version remains immutable/history and cannot answer through the
// current UI until replacement ACK.
export type JourneyAction =
  | 'advance_reading'
  | 'advance_admission'
  | 'advance_processing'
  | 'land_draft'
  | 'correct'
  | 'land_revision'
  | 'confirm'
  | 'answer'
  | 'request_cancel'
  | 'complete_cancel'
  | 'fail_spent'
  | 'error'
  | 'evidence_missing'
  | 'invalidate';

const TRANSITIONS: Record<ReplacementState, Partial<Record<JourneyAction, ReplacementState>>> = {
  uploading: {
    advance_reading: 'awaiting_original_reading',
    request_cancel: 'cancel_requested',
    error: 'error',
  },
  awaiting_original_reading: {
    advance_admission: 'awaiting_admission',
    request_cancel: 'cancel_requested',
    error: 'error',
    evidence_missing: 'evidence_missing',
  },
  awaiting_admission: {
    advance_processing: 'processing',
    request_cancel: 'cancel_requested',
    error: 'error',
  },
  processing: {
    land_draft: 'draft_ready',
    request_cancel: 'cancel_requested',
    fail_spent: 'failed_spent',
    error: 'error',
    evidence_missing: 'evidence_missing',
  },
  draft_ready: {
    correct: 'revision_pending',
    confirm: 'confirmed_for_scope',
    request_cancel: 'cancel_requested',
    error: 'error',
  },
  revision_pending: {
    land_revision: 'draft_ready',
    request_cancel: 'cancel_requested',
    fail_spent: 'failed_spent',
    error: 'error',
  },
  confirmed_for_scope: {
    answer: 'answer_ready',
    correct: 'revision_pending',
    request_cancel: 'cancel_requested',
    invalidate: 'draft_ready',
    error: 'error',
  },
  answer_ready: {
    correct: 'revision_pending',
    request_cancel: 'cancel_requested',
    invalidate: 'confirmed_for_scope',
    error: 'error',
  },
  cancel_requested: {
    complete_cancel: 'cancelled',
    fail_spent: 'failed_spent',
  },
  cancelled: {},
  failed_spent: {},
  error: {},
  evidence_missing: {
    advance_processing: 'processing',
    error: 'error',
  },
};

export function nextReplacementState(
  from: ReplacementState,
  action: JourneyAction,
): ReplacementState | null {
  assertKnownState(from);
  const table = TRANSITIONS[from];
  return table[action] ?? null;
}

export function canApplyJourneyAction(
  from: ReplacementState,
  action: JourneyAction,
): boolean {
  return nextReplacementState(from, action) !== null;
}

/** Terminal states never accept further promotion or replay. */
export function isTerminalReplacementState(state: ReplacementState): boolean {
  return state === 'cancelled' || state === 'failed_spent' || state === 'error';
}

/** Documented labels for the workspace state machine (display only). */
export const REPLACEMENT_STATE_LABELS: Record<ReplacementState, string> = {
  uploading: 'Uploading',
  awaiting_original_reading: 'Awaiting original reading',
  awaiting_admission: 'Awaiting admission',
  processing: 'Processing',
  draft_ready: 'Draft ready',
  revision_pending: 'Revision pending',
  confirmed_for_scope: 'Confirmed for scope',
  answer_ready: 'Answer ready',
  cancel_requested: 'Cancel requested',
  cancelled: 'Cancelled',
  failed_spent: 'Failed (spent)',
  error: 'Error',
  evidence_missing: 'Evidence missing',
};
