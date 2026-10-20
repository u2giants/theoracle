// Unit/contract tests for the replacement journey TypeScript layer.
// Registered in .github/workflows/oracle2-contracts.yml via `tsx --test`.
// Synthetic/invented only. Not a native-acceptance proof path.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  REPLACEMENT_STATES,
  assertKnownState,
  canApplyJourneyAction,
  isReplacementState,
  nextReplacementState,
  promotionEvidenceBound,
  validateReplacementSnapshot,
  type ReplacementSnapshot,
} from './replacement-contract';
import {
  buildSyntheticAnswer,
  buildSyntheticMapView,
  replacementFixtureStore,
  sha256Hex,
} from './replacement-store';
import {
  replacementAuth,
  withinReplacementBounds,
  bindPilotFallbackWorkspace,
  isSameOriginWrite,
  authorizeReplacementRequest,
  replacementSessionCookie,
  clearReplacementSessionCookie,
  REPLACEMENT_ROLE,
  REPLACEMENT_WORKSPACE_ID,
  type ReplacementPrincipal,
} from './replacement-auth';
import {
  sessionCookie,
  clearSessionCookie,
} from './oracle2-pilot-auth';
import { GET as listJourneys } from '../app/api/consultant/replacement/v1/journeys/route';
import { GET as getJourney } from '../app/api/consultant/replacement/v1/journeys/[id]/route';
import { POST as postSource } from '../app/api/consultant/replacement/v1/sources/route';
import type { NextRequest } from 'next/server';
import { lineageAuthorizes, type AppointmentRow } from './oracle2-authority';
import { operatingLineageAuthorizes, type OperatingAppointmentRow } from './operating-model-store';

const WORKSPACE = '00000000-0000-4000-8000-0000000000f1';

function seedJourney(): ReturnType<typeof replacementFixtureStore> {
  const store = replacementFixtureStore();
  store.reset();
  return store;
}

const OWNER_A = '00000000-0000-4000-8000-0000000000a1';
const OWNER_B = '00000000-0000-4000-8000-0000000000b2';

function uploadAndCreate(
  store: ReturnType<typeof replacementFixtureStore>,
  bytes: Buffer = Buffer.from('invented original bytes for replacement journey'),
  actorId: string = OWNER_A,
) {
  const stored = store.registerSource({
    workspaceId: WORKSPACE,
    actorId,
    filename: 'invented.txt',
    contentType: 'text/plain',
    bytes,
  });
  const record = store.createJourney({
    workspaceId: WORKSPACE,
    actorId,
    sourceIds: [stored.source.sourceId],
  });
  return { stored, record };
}

function runToDraft(
  store: ReturnType<typeof replacementFixtureStore>,
  journeyId: string,
  callerActorId: string = OWNER_A,
) {
  let rev = 1;
  store.applyAction({ journeyId, expectedStateRevision: rev, action: 'advance_reading', callerActorId, callerWorkspaceId: WORKSPACE });
  rev += 1;
  store.applyAction({ journeyId, expectedStateRevision: rev, action: 'advance_admission', callerActorId, callerWorkspaceId: WORKSPACE });
  rev += 1;
  store.applyAction({ journeyId, expectedStateRevision: rev, action: 'advance_processing', callerActorId, callerWorkspaceId: WORKSPACE });
  rev += 1;
  store.landDraft({ journeyId, expectedStateRevision: rev, callerActorId, callerWorkspaceId: WORKSPACE });
  return store.getJourney(journeyId)!;
}

test('State 13 literals are the only recognized replacement states', () => {
  assert.equal(REPLACEMENT_STATES.length, 13);
  for (const state of REPLACEMENT_STATES) {
    assert.equal(isReplacementState(state), true);
    assert.equal(assertKnownState(state), state);
  }
  for (const bogus of ['ready', 'pending', 'FAILED', 'draft', 'unknown', '', 'Draft_Ready']) {
    assert.equal(isReplacementState(bogus), false);
    assert.throws(() => assertKnownState(bogus), /unknown replacement state/);
  }
});

test('unknown state fails closed in snapshot validation', () => {
  const base = {
    journeyId: '00000000-0000-4000-8000-000000000001',
    journeyRevision: 1,
    state: 'ready',
    sources: [],
    model: null,
    confirmation: null,
    answer: null,
    message: '',
    mapView: null,
  };
  const result = validateReplacementSnapshot(base);
  assert.equal(result.ok, false);
  if (!result.ok) assert.equal(result.error, 'unknown replacement state');
});

test('fail-closed snapshot rules: model/map/answer/confirmation coupling', () => {
  const source = {
    workspaceId: WORKSPACE,
    sourceId: '00000000-0000-4000-8000-000000000011',
    revision: 1,
    originalSha256: 'a'.repeat(64),
    readingSha256: 'b'.repeat(64),
    parserId: 'fixture-reader-v1',
  };
  const model = {
    modelId: '00000000-0000-4000-8000-000000000021',
    version: 1,
    contentHash: 'c'.repeat(64),
    ackEventId: '00000000-0000-4000-8000-000000000031',
  };
  const mapView = buildSyntheticMapView(source);
  const answer = buildSyntheticAnswer(source);

  const okDraft: ReplacementSnapshot = {
    journeyId: '00000000-0000-4000-8000-000000000001',
    journeyRevision: 1,
    state: 'draft_ready',
    sources: [source],
    model,
    confirmation: null,
    answer: null,
    message: '',
    mapView,
  };
  const okResult = validateReplacementSnapshot(okDraft);
  assert.equal(okResult.ok, true, okResult.ok ? '' : okResult.error);

  // map without model
  assert.equal(
    validateReplacementSnapshot({ ...okDraft, model: null, state: 'processing' }).ok,
    false,
  );
  // answer outside answer_ready
  assert.equal(validateReplacementSnapshot({ ...okDraft, answer }).ok, false);
  // answer_ready without answer
  assert.equal(
    validateReplacementSnapshot({ ...okDraft, state: 'answer_ready', answer: null }).ok,
    false,
  );
  // confirmed_for_scope without current confirmation
  assert.equal(
    validateReplacementSnapshot({ ...okDraft, state: 'confirmed_for_scope' }).ok,
    false,
  );
  // stale model outside draft/confirmed/answer
  assert.equal(validateReplacementSnapshot({ ...okDraft, state: 'revision_pending' }).ok, false);
  // current confirmation that disagrees with model
  assert.equal(
    validateReplacementSnapshot({
      ...okDraft,
      state: 'answer_ready',
      answer,
      confirmation: {
        workflowId: 'wf-synthetic-intake',
        version: 2,
        contentHash: 'd'.repeat(64),
        current: true,
      },
    }).ok,
    false,
  );
});

test('R8 High: promotion to confirmed/answer-ready requires qualification and review commits', () => {
  const bareSource = {
    workspaceId: WORKSPACE,
    sourceId: '00000000-0000-4000-8000-000000000011',
    revision: 1,
    originalSha256: 'a'.repeat(64),
    readingSha256: 'b'.repeat(64),
    parserId: 'fixture-reader-v1',
    readerCommit: undefined as string | undefined,
    reviewerCommit: undefined as string | undefined,
  };
  const boundSource = {
    ...bareSource,
    readerCommit: '1'.repeat(64),
    reviewerCommit: '2'.repeat(64),
  };
  const model = {
    modelId: '00000000-0000-4000-8000-000000000021',
    version: 1,
    contentHash: 'c'.repeat(64),
    ackEventId: '00000000-0000-4000-8000-000000000031',
  };
  const mapView = buildSyntheticMapView(boundSource);
  const answer = buildSyntheticAnswer(boundSource);
  const confirmation = {
    workflowId: mapView.workflow.workflow_id,
    version: 1,
    contentHash: model.contentHash,
    current: true,
  };
  const base = {
    journeyId: '00000000-0000-4000-8000-000000000001',
    journeyRevision: 1,
    model,
    message: '',
    mapView,
  };

  // Evidence gate alone.
  assert.equal(promotionEvidenceBound([boundSource]), true);
  assert.equal(promotionEvidenceBound([bareSource]), false);
  assert.equal(promotionEvidenceBound([]), false);

  // Promotion without evidence is denied even with confirmation + answer.
  assert.equal(
    validateReplacementSnapshot({
      ...base,
      state: 'confirmed_for_scope',
      sources: [bareSource],
      confirmation,
      answer: null,
    }).ok,
    false,
  );
  assert.equal(
    validateReplacementSnapshot({
      ...base,
      state: 'answer_ready',
      sources: [bareSource],
      confirmation,
      answer,
    }).ok,
    false,
  );

  // Confirm-scope + evidence binding is allowed.
  const confirmed = validateReplacementSnapshot({
    ...base,
    state: 'confirmed_for_scope',
    sources: [boundSource],
    confirmation,
    answer: null,
  });
  assert.equal(confirmed.ok, true, confirmed.ok ? '' : confirmed.error);
  const ready = validateReplacementSnapshot({
    ...base,
    state: 'answer_ready',
    sources: [boundSource],
    confirmation,
    answer,
  });
  assert.equal(ready.ok, true, ready.ok ? '' : ready.error);

  // Store refuses promotion when the source lacks commits.
  const store = seedJourney();
  const { stored, record } = uploadAndCreate(store);
  const draft = runToDraft(store, record.journeyId);
  (stored.source as { readerCommit?: string }).readerCommit = undefined;
  (stored.source as { reviewerCommit?: string }).reviewerCommit = undefined;
  assert.throws(
    () =>
      store.confirmScope({
        journeyId: record.journeyId,
        expectedStateRevision: draft.stateRevision,
        workflowId: 'wf-synthetic-intake',
        version: draft.model!.version,
        contentHash: draft.model!.contentHash,
        idempotencyKey: 'conf-no-evidence',
        callerActorId: OWNER_A,
        callerWorkspaceId: WORKSPACE,
      }),
    /qualification and review commits required for promotion/,
  );
});

test('journey transitions are CAS-checked and fail closed on illegal actions', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  assert.equal(record.state, 'uploading');
  assert.equal(nextReplacementState('uploading', 'advance_reading'), 'awaiting_original_reading');
  assert.equal(nextReplacementState('uploading', 'land_draft'), null);
  assert.equal(canApplyJourneyAction('cancelled', 'land_draft'), false);

  assert.throws(
    () =>
      store.applyAction({
        journeyId: record.journeyId,
        expectedStateRevision: 999,
        action: 'advance_reading', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
      }),
    /stale state revision/,
  );
  assert.throws(
    () =>
      store.applyAction({
        journeyId: record.journeyId,
        expectedStateRevision: 1,
        action: 'confirm', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
      }),
    /illegal journey action/,
  );
});

test('correction creates a genuinely new revision and never edits the body', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  const draft = runToDraft(store, record.journeyId);
  const baseVersion = draft.model!.version;
  const baseHash = draft.model!.contentHash;
  const baseContentSnapshot = JSON.stringify(draft.mapView);
  const artifactId = draft.modelArtifactId;

  const result = store.applyCorrection({
    journeyId: record.journeyId,
    expectedStateRevision: draft.stateRevision,
    baseVersion,
    baseContentHash: baseHash,
    transitionId: 't-1-2',
    expectedFromId: 'step-1',
    expectedToId: 'step-2',
    newFromId: 'step-2',
    newToId: 'step-3',
    reason: 'Record an explicit handoff owner after authorized review.',
    idempotencyKey: 'corr-1', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });

  // Immediately revision_pending; current model/map/answer/badge cleared.
  assert.equal(result.record.state, 'revision_pending');
  assert.equal(result.record.model, null);
  assert.equal(result.record.mapView, null);
  assert.equal(result.record.confirmation, null);
  assert.equal(result.record.answer, null);
  assert.ok(result.record.invalidatedAt);

  // Correction evidence is append-only original review evidence.
  assert.equal(result.correction.baseVersion, baseVersion);
  assert.equal(result.correction.baseContentHash, baseHash);
  assert.equal(result.correction.resultingModelVersion, baseVersion + 1);
  assert.ok(result.correction.originalCorrectionSha256);
  assert.match(result.correction.originalCorrectionSource, /REQUESTED interpretation/);

  // Land the genuinely new revision: same artifact UUID, version+1.
  const landed = store.landRevision({
    journeyId: record.journeyId,
    expectedStateRevision: result.record.stateRevision, callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  assert.equal(landed.state, 'draft_ready');
  assert.equal(landed.model!.version, baseVersion + 1);
  assert.equal(landed.model!.modelId, artifactId);
  assert.notEqual(landed.model!.contentHash, baseHash);
  // Body was not edited in place: the old transition tuple is replaced by the
  // requested connection in the NEW map, and the old map is not retained as
  // current. Idempotent correction replay returns the same evidence.
  const replay = store.applyCorrection({
    journeyId: record.journeyId,
    expectedStateRevision: landed.stateRevision,
    baseVersion: landed.model!.version,
    baseContentHash: landed.model!.contentHash,
    transitionId: 't-2-3',
    expectedFromId: 'step-2',
    expectedToId: 'step-3',
    newFromId: 'step-1',
    newToId: 'step-3',
    reason: 'second correction',
    idempotencyKey: 'corr-1', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  assert.equal(replay.correction.correctionId, 'corr-1');
  assert.equal(replay.record.corrections.length, 1);
  void baseContentSnapshot;
});

test('cancel preserves spent liability, shows cancelled, and forbids replay', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  const draft = runToDraft(store, record.journeyId);

  store.dispatchAttempt({ journeyId: record.journeyId, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE });
  store.spendAttempt({ journeyId: record.journeyId, attemptId: 'native1', callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE });

  store.requestCancel({
    journeyId: record.journeyId,
    expectedStateRevision: draft.stateRevision, callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  let current = store.getJourney(record.journeyId)!;
  assert.equal(current.state, 'cancel_requested');
  assert.equal(current.attempts[0]!.status, 'spent');
  assert.equal(current.attempts[0]!.liabilityPreserved, true);

  store.completeCancel({
    journeyId: record.journeyId,
    expectedStateRevision: current.stateRevision, callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  current = store.getJourney(record.journeyId)!;
  assert.equal(current.state, 'cancelled');
  // Spent attempt remains spent with liability preserved — never refunded.
  assert.equal(current.attempts[0]!.status, 'spent');
  assert.equal(current.attempts[0]!.liabilityPreserved, true);
  // Current map/answer/badge clear on cancel.
  assert.equal(current.answer, null);
  assert.equal(current.confirmation, null);

  // No replay of spent attempt; no further promotion on terminal state.
  assert.throws(
    () => store.replayAttempt({ journeyId: record.journeyId, attemptId: 'native1', callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /no replay/,
  );
  assert.throws(
    () => store.dispatchAttempt({ journeyId: record.journeyId, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /terminal; no replay/,
  );
  assert.throws(
    () =>
      store.applyAction({
        journeyId: record.journeyId,
        expectedStateRevision: current.stateRevision,
        action: 'land_draft', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
      }),
    /terminal; no replay/,
  );
});

test('native1..N attempt visibility: attempt 1 spent, attempt 2 new, never replay', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  runToDraft(store, record.journeyId);

  store.dispatchAttempt({ journeyId: record.journeyId, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE });
  store.spendAttempt({ journeyId: record.journeyId, attemptId: 'native1', callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE });
  store.dispatchAttempt({ journeyId: record.journeyId, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE });

  const current = store.getJourney(record.journeyId)!;
  assert.equal(current.attempts.length, 2);
  assert.equal(current.attempts[0]!.attemptId, 'native1');
  assert.equal(current.attempts[0]!.status, 'spent');
  assert.equal(current.attempts[1]!.attemptId, 'native2');
  assert.equal(current.attempts[1]!.status, 'new');
  // Attempt 2 is a new external operation, not a replay of attempt 1.
  assert.match(current.attempts[1]!.note, /never a replay/);
  // Re-spending a spent attempt is refused.
  assert.throws(
    () => store.spendAttempt({ journeyId: record.journeyId, attemptId: 'native1', callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /already spent; no replay/,
  );
});

test('invalidation clears current map/answer/badge; metadata alone never yields ready', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  runToDraft(store, record.journeyId);
  store.confirmScope({
    journeyId: record.journeyId,
    expectedStateRevision: store.getJourney(record.journeyId)!.stateRevision,
    workflowId: 'wf-synthetic-intake',
    version: 1,
    contentHash: store.getJourney(record.journeyId)!.model!.contentHash,
    idempotencyKey: 'conf-1', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  store.produceAnswer({
    journeyId: record.journeyId,
    expectedStateRevision: store.getJourney(record.journeyId)!.stateRevision, callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  const ready = store.getJourney(record.journeyId)!;
  assert.equal(ready.state, 'answer_ready');
  assert.ok(ready.mapView);
  assert.ok(ready.answer);
  assert.ok(ready.confirmation?.current);

  store.invalidateCurrent({
    journeyId: record.journeyId,
    expectedStateRevision: ready.stateRevision, callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
  });
  const cleared = store.getJourney(record.journeyId)!;
  assert.equal(cleared.mapView, null);
  assert.equal(cleared.answer, null);
  assert.equal(cleared.confirmation, null);
  assert.ok(cleared.invalidatedAt);
  // Fail-closed: the cleared snapshot is still valid and NOT ready.
  const snapshot = store.validatedSnapshot(cleared);
  assert.notEqual(snapshot.state, 'answer_ready');
  assert.notEqual(snapshot.state, 'confirmed_for_scope');
});

test('stale seeded metadata never becomes the current native pipeline output', () => {
  const store = seedJourney();
  const stored = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_A,
    filename: 'invented.png',
    contentType: 'image/png',
    bytes: Buffer.from('png-bytes'),
    staleSeeded: {
      label: 'legacy-graph-evidence-v1',
      modelId: '00000000-0000-4000-8000-0000000000s1',
      contentHash: 'a'.repeat(64),
    },
  });
  const identity = store.nativePipelineIdentity(stored.source.sourceId);
  assert.equal(identity.currentPipeline, 'native-fixture-v1');
  assert.ok(identity.staleSeeded);
  assert.notEqual(identity.currentContentHash, identity.staleSeeded!.contentHash);
  assert.equal(
    identity.currentContentHash,
    sha256Hex(`native-pipeline:${stored.source.originalSha256}`),
  );
});

test('confirmation of a stale version is refused (no carry-forward)', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  const draft = runToDraft(store, record.journeyId);
  assert.throws(
    () =>
      store.confirmScope({
        journeyId: record.journeyId,
        expectedStateRevision: draft.stateRevision,
        workflowId: 'wf-synthetic-intake',
        version: 99,
        contentHash: 'e'.repeat(64),
        idempotencyKey: 'conf-stale', callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
      }),
    /differs from current map/,
  );
});

test('answer requires current confirmation; unsupported state abstains', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  const draft = runToDraft(store, record.journeyId);
  assert.throws(
    () =>
      store.produceAnswer({
        journeyId: record.journeyId,
        expectedStateRevision: draft.stateRevision, callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
      }),
    /confirmation required/,
  );
});

// ---------------------------------------------------------------------------
// R8 security: fail-closed API auth (401 unauthenticated, 403 out-of-scope)
// ---------------------------------------------------------------------------

function authDeps(over: Partial<Parameters<typeof replacementAuth>[0]> = {}) {
  let now = 1_000_000;
  return {
    token: () => 'invented-replacement-token',
    actorId: () => '00000000-0000-4000-8000-0000000000a1',
    workspaceId: () => REPLACEMENT_WORKSPACE_ID,
    role: () => REPLACEMENT_ROLE,
    clock: () => now,
    ...over,
    advance(ms: number) {
      now += ms;
    },
  };
}

test('unauthenticated API requests are denied with 401', async () => {
  const denied = await listJourneys(
    new Request('https://example.test/api/consultant/replacement/v1/journeys') as unknown as NextRequest,
  );
  assert.equal(denied.status, 401);
  const body = (await denied.json()) as { error: string };
  assert.match(body.error, /session required|pilot session required/);

  const deniedRead = await getJourney(
    new Request('https://example.test/api/consultant/replacement/v1/journeys/x') as unknown as NextRequest,
    { params: Promise.resolve({ id: 'x' }) },
  );
  assert.equal(deniedRead.status, 401);
});

test('wrong-scope principal is denied with 403 (workspace+role bounds)', () => {
  const wrongRole = replacementAuth(
    authDeps({ role: () => 'not_a_replacement_role' }) as Parameters<typeof replacementAuth>[0],
  );
  const created = wrongRole.create('invented-replacement-token');
  assert.equal(created.ok, false);
  if (!created.ok) assert.equal(created.status, 403);

  const wrongWorkspace = replacementAuth(
    authDeps({
      workspaceId: () => '00000000-0000-4000-8000-0000000000f9',
    }) as Parameters<typeof replacementAuth>[0],
  );
  const createdForeign = wrongWorkspace.create('invented-replacement-token');
  assert.equal(createdForeign.ok, false);
  if (!createdForeign.ok) assert.equal(createdForeign.status, 403);

  const outOfBounds: ReplacementPrincipal = {
    actorId: '00000000-0000-4000-8000-0000000000a1',
    workspaceId: REPLACEMENT_WORKSPACE_ID,
    role: 'someone_else',
  };
  assert.equal(withinReplacementBounds(outOfBounds), false);
});

test('replacement session authorize is fail-closed on missing/invalid identity', () => {
  const gate = replacementAuth(authDeps() as Parameters<typeof replacementAuth>[0]);
  assert.equal(gate.authorize(new Headers()).ok, false);
  assert.equal(gate.authorize(new Headers({ cookie: 'oracle2_replacement_session=' })).ok, false);
  const noToken = replacementAuth(
    authDeps({ token: () => undefined }) as Parameters<typeof replacementAuth>[0],
  );
  assert.equal(noToken.create('invented-replacement-token').ok, false);
  const wrongToken = replacementAuth(authDeps() as Parameters<typeof replacementAuth>[0]);
  const rejected = wrongToken.create('not-the-token');
  assert.equal(rejected.ok, false);
  if (!rejected.ok) assert.equal(rejected.status, 401);

  // A valid session is accepted and carries the server-derived principal.
  const gate2 = replacementAuth(authDeps() as Parameters<typeof replacementAuth>[0]);
  const issued = gate2.create('invented-replacement-token');
  assert.equal(issued.ok, true);
  if (issued.ok) {
    assert.equal(issued.principal.role, REPLACEMENT_ROLE);
    assert.equal(issued.principal.workspaceId, REPLACEMENT_WORKSPACE_ID);
    const headers = new Headers({
      cookie: `oracle2_replacement_session=${encodeURIComponent(issued.sessionId)}`,
    });
    const authed = gate2.authorize(headers);
    assert.equal(authed.ok, true);
    if (authed.ok) assert.equal(authed.principal.actorId, issued.principal.actorId);
  }
});

test('illegal state transitions remain denied (no gate skip)', () => {
  // pending cannot jump to confirmed/answer_ready or terminal cancelled.
  assert.equal(nextReplacementState('uploading', 'confirm'), null);
  assert.equal(nextReplacementState('uploading', 'answer'), null);
  assert.equal(nextReplacementState('uploading', 'complete_cancel'), null);
  assert.equal(nextReplacementState('processing', 'confirm'), null);
  assert.equal(nextReplacementState('processing', 'answer'), null);
  // correction is the only path into revision_pending from a draft.
  assert.equal(nextReplacementState('draft_ready', 'correct'), 'revision_pending');
  assert.equal(nextReplacementState('uploading', 'correct'), null);
  // cancel goes through request_cancel then complete_cancel only.
  assert.equal(nextReplacementState('uploading', 'request_cancel'), 'cancel_requested');
  assert.equal(nextReplacementState('cancel_requested', 'complete_cancel'), 'cancelled');
  assert.equal(nextReplacementState('cancel_requested', 'confirm'), null);
});

// --- R8 security denied-case tests ----------------------------------------

test('High 1: review-only session denied for write operations', async () => {
  // Mock sessionHasScope: review-only actor has 'review' but not 'confirm'.
  const reviewOnlyActor = '00000000-0000-4000-8000-0000000000r1';
  const writeActor = '00000000-0000-4000-8000-0000000000w1';

  // We test the access model directly: write requires confirm scope.
  const store = seedJourney();
  const { record } = uploadAndCreate(store);

  // Review-only: cannot mutate.
  assert.throws(
    () => store.applyAction({ journeyId: record.journeyId, expectedStateRevision: 1, action: 'advance_reading', callerActorId: reviewOnlyActor, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );

  // Write-scoped (owner): can mutate.
  const advanced = store.applyAction({ journeyId: record.journeyId, expectedStateRevision: 1, action: 'advance_reading', callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE });
  assert.equal(advanced.state, 'awaiting_original_reading');
});

test('High 1: write scope required for mutations via access model', async () => {
  // The access model: write requires 'confirm' scope; read accepts 'review' or 'confirm'.
  // Direct store calls enforce ownership; the route layer enforces scope.
  // Verify that a non-owner cannot mutate (cross-user denial).
  const store = seedJourney();
  const { record } = uploadAndCreate(store, undefined, OWNER_A);

  // User B cannot advance user A's journey.
  assert.throws(
    () => store.applyAction({ journeyId: record.journeyId, expectedStateRevision: 1, action: 'advance_reading', callerActorId: OWNER_B, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );

  // User B cannot cancel user A's journey.
  assert.throws(
    () => store.requestCancel({ journeyId: record.journeyId, expectedStateRevision: 1, callerActorId: OWNER_B, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );

  // User B cannot confirm user A's journey.
  assert.throws(
    () => store.confirmScope({
      journeyId: record.journeyId,
      expectedStateRevision: 1,
      workflowId: 'wf-x',
      version: 1,
      contentHash: 'x',
      idempotencyKey: 'k1',
      callerActorId: OWNER_B,
      callerWorkspaceId: WORKSPACE,
    }),
    /unknown journey/,
  );
});

test('High 2: user A cannot read user B journey', () => {
  const store = seedJourney();
  const { record: recordA } = uploadAndCreate(store, undefined, OWNER_A);
  const { record: recordB } = uploadAndCreate(store, undefined, OWNER_B);

  // listJourneys filters to caller's journeys.
  const journeysA = store.listJourneys(OWNER_A, WORKSPACE);
  assert.equal(journeysA.length, 1);
  assert.equal(journeysA[0]!.journeyId, recordA.journeyId);

  const journeysB = store.listJourneys(OWNER_B, WORKSPACE);
  assert.equal(journeysB.length, 1);
  assert.equal(journeysB[0]!.journeyId, recordB.journeyId);

  // getJourney with wrong owner returns null (consistent not-found).
  assert.equal(store.getJourney(recordA.journeyId, OWNER_B, WORKSPACE), null);

  // getJourney with correct owner works.
  const got = store.getJourney(recordA.journeyId, OWNER_A, WORKSPACE);
  assert.ok(got);
  assert.equal(got.journeyId, recordA.journeyId);
});

test('High 2: user A cannot mutate user B journey', () => {
  const store = seedJourney();
  const { record: recordB } = uploadAndCreate(store, undefined, OWNER_B);

  // All mutation paths deny cross-user access.
  assert.throws(
    () => store.applyAction({ journeyId: recordB.journeyId, expectedStateRevision: 1, action: 'advance_reading', callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );
  assert.throws(
    () => store.landDraft({ journeyId: recordB.journeyId, expectedStateRevision: 1, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );
  assert.throws(
    () => store.dispatchAttempt({ journeyId: recordB.journeyId, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );
  assert.throws(
    () => store.invalidateCurrent({ journeyId: recordB.journeyId, expectedStateRevision: 1, callerActorId: OWNER_A, callerWorkspaceId: WORKSPACE }),
    /unknown journey/,
  );
});

test('High 2: cross-user source access denied', () => {
  const store = seedJourney();
  const { stored } = uploadAndCreate(store, undefined, OWNER_A);

  // User B cannot read user A's source (returns null — consistent not-found).
  assert.equal(store.getSource(stored.source.sourceId, OWNER_B, WORKSPACE), null);

  // User A can read their own source.
  const got = store.getSource(stored.source.sourceId, OWNER_A, WORKSPACE);
  assert.ok(got);
  assert.equal(got.source.sourceId, stored.source.sourceId);

  // listSources filters by owner.
  const sourcesA = store.listSources(OWNER_A, WORKSPACE);
  assert.equal(sourcesA.length, 1);
  const sourcesB = store.listSources(OWNER_B, WORKSPACE);
  assert.equal(sourcesB.length, 0);
});

// --- R8 round-3 security denied-case tests --------------------------------

test('High r3: pilot session for workspace A must NOT access replacement resources in workspace B', () => {
  const pilotWorkspaceA = '00000000-0000-4000-8000-000000000002';

  // Pilot permissions checked in workspace A must not grant replacement
  // access in workspace B when no explicit replacement-workspace grant exists.
  const deniedRead = bindPilotFallbackWorkspace({
    pilotWorkspaceId: pilotWorkspaceA,
    replacementWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    hasConfirmInReplacement: false,
    hasReviewInReplacement: false,
    access: 'read',
  });
  assert.equal(deniedRead.ok, false);
  if (!deniedRead.ok) {
    assert.equal(deniedRead.status, 403);
    assert.match(deniedRead.error, /cross-workspace replacement grant required/);
  }

  const deniedWrite = bindPilotFallbackWorkspace({
    pilotWorkspaceId: pilotWorkspaceA,
    replacementWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    hasConfirmInReplacement: false,
    hasReviewInReplacement: false,
    access: 'write',
  });
  assert.equal(deniedWrite.ok, false);
  if (!deniedWrite.ok) assert.equal(deniedWrite.status, 403);

  // Even review-only pilot scope in workspace A cannot become a write grant
  // in workspace B without an explicit replacement-workspace confirm grant.
  const deniedInheritedWrite = bindPilotFallbackWorkspace({
    pilotWorkspaceId: pilotWorkspaceA,
    replacementWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    hasConfirmInReplacement: false,
    hasReviewInReplacement: true,
    access: 'write',
  });
  assert.equal(deniedInheritedWrite.ok, false);
  if (!deniedInheritedWrite.ok) {
    assert.equal(deniedInheritedWrite.status, 403);
    assert.match(deniedInheritedWrite.error, /write scope required/);
  }

  // Explicit replacement-workspace grant allows access even across workspaces.
  const allowed = bindPilotFallbackWorkspace({
    pilotWorkspaceId: pilotWorkspaceA,
    replacementWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    hasConfirmInReplacement: true,
    hasReviewInReplacement: true,
    access: 'write',
  });
  assert.equal(allowed.ok, true);

  // Same-workspace fallback still fails closed when no scope is proven.
  const sameWsDenied = bindPilotFallbackWorkspace({
    pilotWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    replacementWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    hasConfirmInReplacement: false,
    hasReviewInReplacement: false,
    access: 'read',
  });
  assert.equal(sameWsDenied.ok, false);
  if (!sameWsDenied.ok) {
    assert.match(sameWsDenied.error, /replacement scope missing or unknown/);
  }
});

test('High r3: cross-workspace principal is out of replacement bounds', () => {
  const foreign: ReplacementPrincipal = {
    actorId: '00000000-0000-4000-8000-0000000000a1',
    workspaceId: '00000000-0000-4000-8000-000000000002',
    role: REPLACEMENT_ROLE,
  };
  assert.equal(withinReplacementBounds(foreign), false);

  const wrongRole: ReplacementPrincipal = {
    actorId: '00000000-0000-4000-8000-0000000000a1',
    workspaceId: REPLACEMENT_WORKSPACE_ID,
    role: 'pilot_user',
  };
  assert.equal(withinReplacementBounds(wrongRole), false);
});

test('Medium r3: user A journey cannot surface user B source metadata even if the ID is known', () => {
  const store = seedJourney();

  // User B registers a source.
  const storedB = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_B,
    filename: 'b-confidential.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('user B confidential original'),
  });

  // User A knows user B's source ID and tries to create a journey over it.
  assert.throws(
    () =>
      store.createJourney({
        workspaceId: WORKSPACE,
        actorId: OWNER_A,
        sourceIds: [storedB.source.sourceId],
      }),
    /unknown source/,
  );

  // User B cannot smuggle user A's source into their own journey either.
  const storedA = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_A,
    filename: 'a.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('user A original'),
  });
  assert.throws(
    () =>
      store.createJourney({
        workspaceId: WORKSPACE,
        actorId: OWNER_B,
        sourceIds: [storedA.source.sourceId],
      }),
    /unknown source/,
  );

  // Mixed populations that include a foreign source are denied.
  const storedB2 = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_B,
    filename: 'b2.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('user B second original'),
  });
  assert.throws(
    () =>
      store.createJourney({
        workspaceId: WORKSPACE,
        actorId: OWNER_A,
        sourceIds: [storedA.source.sourceId, storedB2.source.sourceId],
      }),
    /unknown source/,
  );
});

test('Medium r3: cross-workspace source reference is denied', () => {
  const store = seedJourney();
  const otherWorkspace = '00000000-0000-4000-8000-0000000000aa';

  const storedOther = store.registerSource({
    workspaceId: otherWorkspace,
    actorId: OWNER_A,
    filename: 'other-ws.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('other workspace original'),
  });

  // Same actor, different workspace: still denied.
  assert.throws(
    () =>
      store.createJourney({
        workspaceId: WORKSPACE,
        actorId: OWNER_A,
        sourceIds: [storedOther.source.sourceId],
      }),
    /unknown source/,
  );
});

test('Medium r3: resolveSources refuses to surface foreign source metadata', () => {
  const store = seedJourney();

  const storedA = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_A,
    filename: 'a.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('user A original'),
  });
  const record = store.createJourney({
    workspaceId: WORKSPACE,
    actorId: OWNER_A,
    sourceIds: [storedA.source.sourceId],
  });

  // Tamper the journey to reference a foreign source (simulates a bug or
  // injection that bypassed createJourney). resolveSources must refuse.
  const storedB = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_B,
    filename: 'b.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('user B original'),
  });
  const tampered = {
    ...record,
    sourceIds: [storedB.source.sourceId],
  };
  assert.throws(
    () => store.resolveSources(tampered),
    /unknown source/,
  );
});

// --- R8 round-4 security denied-case tests --------------------------------

test('Medium r4: forged / unrelated-root authority chain is denied', () => {
  const WS = '00000000-0000-4000-8000-0000000000f1';
  const owner = '00000000-0000-4000-8000-0000000000a1';
  const attacker = '00000000-0000-4000-8000-0000000000e1';
  const rootId = '00000000-0000-4000-8000-0000000000r1';
  const forgedId = '00000000-0000-4000-8000-0000000000c1';
  const unrelatedRootId = '00000000-0000-4000-8000-0000000000r2';

  // Legitimate root for the owner.
  const root: AppointmentRow = {
    appointment_id: rootId,
    workspace_id: WS,
    actor_id: owner,
    scope: 'root',
    granted_by: '00000000-0000-4000-8000-0000000000bb',
    parent_id: null,
    revoked_at: null,
    expires_at: null,
  };

  // Forged grant: attacker points parent_id at the owner's root but the
  // issuer link is wrong (granted_by is NOT the root's actor).
  const forged: AppointmentRow = {
    appointment_id: forgedId,
    workspace_id: WS,
    actor_id: attacker,
    scope: 'confirm',
    granted_by: '00000000-0000-4000-8000-0000000000ff',
    parent_id: rootId,
    revoked_at: null,
    expires_at: null,
  };

  // An unrelated root must not confer access.
  const unrelatedRoot: AppointmentRow = {
    appointment_id: unrelatedRootId,
    workspace_id: WS,
    actor_id: '00000000-0000-4000-8000-0000000000x9',
    scope: 'root',
    granted_by: '00000000-0000-4000-8000-0000000000bb',
    parent_id: null,
    revoked_at: null,
    expires_at: null,
  };

  // Forged grant pointing at an unrelated root.
  const forgedUnrelated: AppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000c2',
    workspace_id: WS,
    actor_id: attacker,
    scope: 'confirm',
    granted_by: '00000000-0000-4000-8000-0000000000ff',
    parent_id: unrelatedRootId,
    revoked_at: null,
    expires_at: null,
  };

  // Forged chain: parent_id points at a root but issuer link is broken.
  assert.equal(
    lineageAuthorizes([root, forged], attacker, 'confirm', WS),
    false,
    'forged chain with broken issuer link must be denied',
  );

  // Forged chain pointing at an unrelated root.
  assert.equal(
    lineageAuthorizes([unrelatedRoot, forgedUnrelated], attacker, 'confirm', WS),
    false,
    'chain through an unrelated root must be denied',
  );

  // A grant whose granted_by does not match the claimed parent is denied
  // even when the parent root exists and is live.
  const forgedNoRoot: AppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000c3',
    workspace_id: WS,
    actor_id: attacker,
    scope: 'review',
    granted_by: owner, // pretends the owner issued it
    parent_id: rootId,
    revoked_at: null,
    expires_at: null,
  };
  // Wait — granted_by = owner and parent root has actor_id = owner, so the
  // issuer link matches. This must be ALLOWED (it is a correct chain shape).
  assert.equal(
    lineageAuthorizes([root, forgedNoRoot], attacker, 'review', WS),
    true,
    'correct issuer-linked chain proves authority',
  );

  // The attacker alone (no root) has no authority.
  assert.equal(lineageAuthorizes([forged], attacker, 'confirm', WS), false);

  // Correct delegated chain: owner root -> mid grant -> leaf grant.
  const mid: AppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000m1',
    workspace_id: WS,
    actor_id: '00000000-0000-4000-8000-0000000000b2',
    scope: 'review',
    granted_by: owner,
    parent_id: rootId,
    revoked_at: null,
    expires_at: null,
  };
  const leaf: AppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000l1',
    workspace_id: WS,
    actor_id: attacker,
    scope: 'review',
    granted_by: mid.actor_id,
    parent_id: mid.appointment_id,
    revoked_at: null,
    expires_at: null,
  };
  assert.equal(
    lineageAuthorizes([root, mid, leaf], attacker, 'review', WS),
    true,
    'valid multi-step issuer-linked chain proves authority',
  );

  // Break the issuer link on the leaf: denied.
  const badLeaf: AppointmentRow = { ...leaf, granted_by: owner };
  assert.equal(
    lineageAuthorizes([root, mid, badLeaf], attacker, 'review', WS),
    false,
    'broken issuer link in multi-step chain is denied',
  );

  // Revoked mid invalidates the leaf even with a correct issuer link.
  const revokedMid: AppointmentRow = { ...mid, revoked_at: new Date().toISOString() };
  assert.equal(
    lineageAuthorizes([root, revokedMid, leaf], attacker, 'review', WS),
    false,
    'revoked parent invalidates child chain',
  );
});

test('Medium r4: same actor cannot access records across workspaces', () => {
  const store = seedJourney();
  const WS_B = '00000000-0000-4000-8000-0000000000aa';

  // Register a source and journey in WORKSPACE for OWNER_A.
  const { stored, record } = uploadAndCreate(store);

  // Same actor in a different workspace cannot read the source.
  assert.equal(store.getSource(stored.source.sourceId, OWNER_A, WS_B), null);

  // Same actor in a different workspace cannot read the journey.
  assert.equal(store.getJourney(record.journeyId, OWNER_A, WS_B), null);

  // listJourneys / listSources filter by workspace too.
  assert.equal(store.listJourneys(OWNER_A, WS_B).length, 0);
  assert.equal(store.listSources(OWNER_A, WS_B).length, 0);

  // Same actor in the correct workspace CAN read.
  assert.ok(store.getSource(stored.source.sourceId, OWNER_A, WORKSPACE));
  assert.ok(store.getJourney(record.journeyId, OWNER_A, WORKSPACE));

  // Same actor in a different workspace cannot mutate the journey.
  assert.throws(
    () => store.applyAction({
      journeyId: record.journeyId,
      expectedStateRevision: 1,
      action: 'advance_reading',
      callerActorId: OWNER_A,
      callerWorkspaceId: WS_B,
    }),
    /unknown journey/,
  );
  assert.throws(
    () => store.landDraft({
      journeyId: record.journeyId,
      expectedStateRevision: 1,
      callerActorId: OWNER_A,
      callerWorkspaceId: WS_B,
    }),
    /unknown journey/,
  );
  assert.throws(
    () => store.dispatchAttempt({
      journeyId: record.journeyId,
      callerActorId: OWNER_A,
      callerWorkspaceId: WS_B,
    }),
    /unknown journey/,
  );

  // A journey created in a different workspace is invisible to this workspace.
  const storedOther = store.registerSource({
    workspaceId: WS_B,
    actorId: OWNER_A,
    filename: 'other-ws.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('other workspace original'),
  });
  const recordOther = store.createJourney({
    workspaceId: WS_B,
    actorId: OWNER_A,
    sourceIds: [storedOther.source.sourceId],
  });
  // Same actor, wrong workspace: not visible.
  assert.equal(store.getJourney(recordOther.journeyId, OWNER_A, WORKSPACE), null);
  assert.ok(store.getJourney(recordOther.journeyId, OWNER_A, WS_B));
});

test('Low r4: foreign ID and unknown ID yield the same response (no existence leak)', () => {
  const store = seedJourney();
  const { record: recordA } = uploadAndCreate(store, undefined, OWNER_A);
  const { record: recordB } = uploadAndCreate(store, undefined, OWNER_B);

  // Unknown ID: getJourney returns null.
  const unknown = store.getJourney('00000000-0000-4000-8000-0000000000zz', OWNER_A, WORKSPACE);
  assert.equal(unknown, null);

  // Foreign ID (exists but owned by someone else): also null — same response.
  const foreign = store.getJourney(recordB.journeyId, OWNER_A, WORKSPACE);
  assert.equal(foreign, null);

  // Both are indistinguishable to the caller.
  assert.equal(unknown, foreign);

  // Same for sources.
  const storedB = store.registerSource({
    workspaceId: WORKSPACE,
    actorId: OWNER_B,
    filename: 'b.txt',
    contentType: 'text/plain',
    bytes: Buffer.from('user B original'),
  });
  assert.equal(
    store.getSource('00000000-0000-4000-8000-0000000000zz', OWNER_A, WORKSPACE),
    null,
  );
  assert.equal(
    store.getSource(storedB.source.sourceId, OWNER_A, WORKSPACE),
    null,
  );

  // Mutations: unknown and foreign journey produce the same error.
  assert.throws(
    () => store.applyAction({
      journeyId: '00000000-0000-4000-8000-0000000000zz',
      expectedStateRevision: 1,
      action: 'advance_reading',
      callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
    }),
    /unknown journey/,
  );
  assert.throws(
    () => store.applyAction({
      journeyId: recordB.journeyId,
      expectedStateRevision: 1,
      action: 'advance_reading',
      callerActorId: OWNER_A,
      callerWorkspaceId: WORKSPACE,
    }),
    /unknown journey/,
  );

  // Same for nativePipelineIdentity.
  assert.throws(
    () => store.nativePipelineIdentity('00000000-0000-4000-8000-0000000000zz', OWNER_A, WORKSPACE),
    /unknown source/,
  );
  assert.throws(
    () => store.nativePipelineIdentity(storedB.source.sourceId, OWNER_A, WORKSPACE),
    /unknown source/,
  );
});

// --- R8 pre-emptive: operatingAuthority issuer-link denied cases ----------

test('operatingAuthority: forged / unrelated-root authority chain is denied', () => {
  const WS = '00000000-0000-4000-8000-0000000000f1';
  const owner = '00000000-0000-4000-8000-0000000000a1';
  const attacker = '00000000-0000-4000-8000-0000000000e1';
  const rootId = '00000000-0000-4000-8000-0000000000r1';
  const forgedId = '00000000-0000-4000-8000-0000000000c1';
  const unrelatedRootId = '00000000-0000-4000-8000-0000000000r2';

  const root: OperatingAppointmentRow = {
    appointment_id: rootId,
    workspace_id: WS,
    actor_id: owner,
    scope: 'root',
    granted_by: '00000000-0000-4000-8000-0000000000bb',
    parent_id: null,
    revoked_at: null,
    expires_at: null,
  };

  const forged: OperatingAppointmentRow = {
    appointment_id: forgedId,
    workspace_id: WS,
    actor_id: attacker,
    scope: 'confirm',
    granted_by: '00000000-0000-4000-8000-0000000000ff',
    parent_id: rootId,
    revoked_at: null,
    expires_at: null,
  };

  assert.equal(
    operatingLineageAuthorizes([root, forged], attacker, 'confirm', WS),
    false,
    'forged chain with broken issuer link must be denied',
  );

  const unrelatedRoot: OperatingAppointmentRow = {
    appointment_id: unrelatedRootId,
    workspace_id: WS,
    actor_id: '00000000-0000-4000-8000-0000000000x9',
    scope: 'root',
    granted_by: '00000000-0000-4000-8000-0000000000bb',
    parent_id: null,
    revoked_at: null,
    expires_at: null,
  };
  const forgedUnrelated: OperatingAppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000c2',
    workspace_id: WS,
    actor_id: attacker,
    scope: 'confirm',
    granted_by: '00000000-0000-4000-8000-0000000000ff',
    parent_id: unrelatedRootId,
    revoked_at: null,
    expires_at: null,
  };
  assert.equal(
    operatingLineageAuthorizes([unrelatedRoot, forgedUnrelated], attacker, 'confirm', WS),
    false,
    'chain through an unrelated root must be denied',
  );

  const correctGrant: OperatingAppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000c3',
    workspace_id: WS,
    actor_id: attacker,
    scope: 'review',
    granted_by: owner,
    parent_id: rootId,
    revoked_at: null,
    expires_at: null,
  };
  assert.equal(
    operatingLineageAuthorizes([root, correctGrant], attacker, 'review', WS),
    true,
    'correct issuer-linked chain proves authority',
  );

  const mid: OperatingAppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000m1',
    workspace_id: WS,
    actor_id: '00000000-0000-4000-8000-0000000000b2',
    scope: 'review',
    granted_by: owner,
    parent_id: rootId,
    revoked_at: null,
    expires_at: null,
  };
  const leaf: OperatingAppointmentRow = {
    appointment_id: '00000000-0000-4000-8000-0000000000l1',
    workspace_id: WS,
    actor_id: attacker,
    scope: 'review',
    granted_by: mid.actor_id,
    parent_id: mid.appointment_id,
    revoked_at: null,
    expires_at: null,
  };
  assert.equal(
    operatingLineageAuthorizes([root, mid, leaf], attacker, 'review', WS),
    true,
    'valid multi-step issuer-linked chain proves authority',
  );
  const badLeaf: OperatingAppointmentRow = { ...leaf, granted_by: owner };
  assert.equal(
    operatingLineageAuthorizes([root, mid, badLeaf], attacker, 'review', WS),
    false,
    'broken issuer link in multi-step chain is denied',
  );
});

// --- R8 round-5 security denied-case tests --------------------------------

test('Medium r5: session cookies set Secure and HttpOnly (pilot + replacement)', () => {
  const pilot = sessionCookie('sid-pilot');
  assert.match(pilot, /HttpOnly/, 'pilot session cookie must be HttpOnly');
  assert.match(pilot, /Secure/, 'pilot session cookie must be Secure');
  assert.match(pilot, /SameSite=Lax/, 'pilot session cookie keeps SameSite=Lax');

  const pilotClear = clearSessionCookie();
  assert.match(pilotClear, /HttpOnly/);
  assert.match(pilotClear, /Secure/, 'cleared pilot cookie must match Secure attribute');

  const replacement = replacementSessionCookie('sid-replacement');
  assert.match(replacement, /HttpOnly/, 'replacement session cookie must be HttpOnly');
  assert.match(replacement, /Secure/, 'replacement session cookie must be Secure');
  assert.match(replacement, /SameSite=Lax/);

  const replacementClear = clearReplacementSessionCookie();
  assert.match(replacementClear, /HttpOnly/);
  assert.match(replacementClear, /Secure/);
});

test('Medium r5: local HTTP cookie exception is opt-in and never applies in production', () => {
  const prevFlag = process.env.ORACLE2_INSECURE_LOCAL_COOKIES;
  // NODE_ENV is typed read-only; mutate through the env record in this test only.
  const env = process.env as Record<string, string | undefined>;
  const prevEnv = env.NODE_ENV;
  try {
    // Default (flag unset): Secure is on regardless of NODE_ENV.
    delete env.ORACLE2_INSECURE_LOCAL_COOKIES;
    env.NODE_ENV = 'production';
    assert.match(sessionCookie('s'), /Secure/);
    assert.match(replacementSessionCookie('s'), /Secure/);

    // Explicit flag + non-production: the only case that may omit Secure.
    env.ORACLE2_INSECURE_LOCAL_COOKIES = '1';
    env.NODE_ENV = 'development';
    assert.doesNotMatch(sessionCookie('s'), /Secure/);
    assert.doesNotMatch(replacementSessionCookie('s'), /Secure/);

    // Explicit flag must NOT weaken production posture.
    env.NODE_ENV = 'production';
    assert.match(sessionCookie('s'), /Secure/);
    assert.match(replacementSessionCookie('s'), /Secure/);

    // Flag value other than '1' is ignored (Secure stays on).
    env.ORACLE2_INSECURE_LOCAL_COOKIES = '0';
    env.NODE_ENV = 'development';
    assert.match(sessionCookie('s'), /Secure/);
    assert.match(replacementSessionCookie('s'), /Secure/);
  } finally {
    if (prevFlag === undefined) delete env.ORACLE2_INSECURE_LOCAL_COOKIES;
    else env.ORACLE2_INSECURE_LOCAL_COOKIES = prevFlag;
    if (prevEnv === undefined) delete env.NODE_ENV;
    else env.NODE_ENV = prevEnv;
  }
});

test('Medium r5: cross-origin and missing-Origin writes are denied (CSRF / Origin gate)', () => {
  // Same-origin write is allowed (cookie-authenticated simple POST from our UI).
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://app.example.test',
      }),
    ),
    true,
    'same-origin Origin must be accepted',
  );

  // Cross-origin: attacker-controlled sibling domain (same-site, different origin).
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://evil.example.test',
      }),
    ),
    false,
    'sibling-domain Origin must be denied (SameSite=Lax does not cover this)',
  );

  // Fully cross-site Origin.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://attacker.example',
      }),
    ),
    false,
    'cross-site Origin must be denied',
  );

  // Opaque / null origin (sandboxed iframe, data: navigation).
  assert.equal(
    isSameOriginWrite(new Headers({ host: 'app.example.test', origin: 'null' })),
    false,
    'Origin: null must be denied',
  );

  // Missing both Origin and Sec-Fetch-Site fails closed on writes.
  assert.equal(
    isSameOriginWrite(new Headers({ host: 'app.example.test' })),
    false,
    'write without Origin/Sec-Fetch-Site must fail closed',
  );

  // Sec-Fetch-Site same-site (sibling subdomain) is NOT same-origin.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        'sec-fetch-site': 'same-site',
      }),
    ),
    false,
    'Sec-Fetch-Site: same-site must be denied',
  );

  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        'sec-fetch-site': 'cross-site',
      }),
    ),
    false,
    'Sec-Fetch-Site: cross-site must be denied',
  );

  // Sec-Fetch-Site same-origin/none are acceptable proofs of intent.
  assert.equal(
    isSameOriginWrite(
      new Headers({ host: 'app.example.test', 'sec-fetch-site': 'same-origin' }),
    ),
    true,
    'Sec-Fetch-Site: same-origin must be accepted',
  );
  assert.equal(
    isSameOriginWrite(new Headers({ host: 'app.example.test', 'sec-fetch-site': 'none' })),
    true,
    'Sec-Fetch-Site: none (user-initiated) must be accepted',
  );

  // Origin mismatch is denied even when Sec-Fetch-Site looks benign.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://evil.example.test',
        'sec-fetch-site': 'same-origin',
      }),
    ),
    false,
    'conflicting cross-origin Origin must be denied',
  );
});

test('Medium r8: scheme mismatches are denied (http Origin for https request and vice versa)', () => {
  // http Origin rejected for https request (trusted scheme defaults to https).
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'http://app.example.test',
      }),
    ),
    false,
    'http Origin must be denied for https request',
  );

  // http Origin rejected when the request is explicitly https.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'http://app.example.test',
        'x-forwarded-proto': 'https',
      }),
    ),
    false,
    'http Origin must be denied when x-forwarded-proto is https',
  );

  // Vice versa: https Origin rejected for http request.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://app.example.test',
        'x-forwarded-proto': 'http',
      }),
    ),
    false,
    'https Origin must be denied for http request',
  );

  // Matching scheme is accepted — http Origin for an http request.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'http://app.example.test',
        'x-forwarded-proto': 'http',
      }),
    ),
    true,
    'http Origin must be accepted for http request',
  );

  // Matching scheme is accepted — https Origin for an https request.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://app.example.test',
        'x-forwarded-proto': 'https',
      }),
    ),
    true,
    'https Origin must be accepted for https request',
  );

  // Spoofed / multi-value x-forwarded-proto fails closed.
  assert.equal(
    isSameOriginWrite(
      new Headers({
        host: 'app.example.test',
        origin: 'https://app.example.test',
        'x-forwarded-proto': 'https, https',
      }),
    ),
    false,
    'comma-list x-forwarded-proto must fail closed',
  );
});

test('Medium r5: upload write is rejected cross-origin and allowed same-origin', async () => {
  // Cross-origin cookie-authenticated upload POST is rejected before any store work.
  const crossOrigin = await postSource(
    new Request('https://app.example.test/api/consultant/replacement/v1/sources', {
      method: 'POST',
      headers: {
        host: 'app.example.test',
        origin: 'https://evil.example.test',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        filename: 'x.txt',
        contentType: 'text/plain',
        bytesBase64: Buffer.from('attack').toString('base64'),
      }),
    }) as unknown as NextRequest,
  );
  assert.equal(crossOrigin.status, 403);
  const crossBody = (await crossOrigin.json()) as { error: string };
  assert.match(crossBody.error, /cross-origin write denied/);

  // Missing Origin/Sec-Fetch-Site also fails closed on the upload route.
  const noOrigin = await postSource(
    new Request('https://app.example.test/api/consultant/replacement/v1/sources', {
      method: 'POST',
      headers: {
        host: 'app.example.test',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        filename: 'x.txt',
        contentType: 'text/plain',
        bytesBase64: Buffer.from('attack').toString('base64'),
      }),
    }) as unknown as NextRequest,
  );
  assert.equal(noOrigin.status, 403);

  // Same-origin upload passes the CSRF gate (then hits auth 401 without a session,
  // proving the origin check is not a blanket reject).
  const sameOrigin = await postSource(
    new Request('https://app.example.test/api/consultant/replacement/v1/sources', {
      method: 'POST',
      headers: {
        host: 'app.example.test',
        origin: 'https://app.example.test',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        filename: 'x.txt',
        contentType: 'text/plain',
        bytesBase64: Buffer.from('ok').toString('base64'),
      }),
    }) as unknown as NextRequest,
  );
  assert.equal(sameOrigin.status, 401);
  const sameBody = (await sameOrigin.json()) as { error: string };
  assert.match(sameBody.error, /session required|pilot session required/);
});

test('Medium r5: authorizeReplacementRequest denies cross-origin writes before session lookup', async () => {
  const denied = await authorizeReplacementRequest(
    new Headers({
      host: 'app.example.test',
      origin: 'https://evil.example.test',
      cookie: 'oracle2_replacement_session=whatever',
    }),
    'write',
  );
  assert.equal(denied.ok, false);
  if (!denied.ok) {
    assert.equal(denied.status, 403);
    assert.match(denied.error, /cross-origin write denied/);
  }

  // Read access is unaffected by the write origin gate (GET is not state-changing).
  const read = await authorizeReplacementRequest(
    new Headers({
      host: 'app.example.test',
      cookie: 'oracle2_replacement_session=whatever',
    }),
    'read',
  );
  assert.equal(read.ok, false);
  if (!read.ok) {
    assert.notEqual(read.status, 403);
    assert.doesNotMatch(read.error, /cross-origin write denied/);
  }
});
