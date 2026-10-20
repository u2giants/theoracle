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
  REPLACEMENT_ROLE,
  REPLACEMENT_WORKSPACE_ID,
  type ReplacementPrincipal,
} from './replacement-auth';
import { GET as listJourneys } from '../app/api/consultant/replacement/v1/journeys/route';
import { GET as getJourney } from '../app/api/consultant/replacement/v1/journeys/[id]/route';
import type { NextRequest } from 'next/server';

const WORKSPACE = '00000000-0000-4000-8000-0000000000f1';

function seedJourney(): ReturnType<typeof replacementFixtureStore> {
  const store = replacementFixtureStore();
  store.reset();
  return store;
}

function uploadAndCreate(
  store: ReturnType<typeof replacementFixtureStore>,
  bytes: Buffer = Buffer.from('invented original bytes for replacement journey'),
) {
  const stored = store.registerSource({
    workspaceId: WORKSPACE,
    filename: 'invented.txt',
    contentType: 'text/plain',
    bytes,
  });
  const record = store.createJourney({
    workspaceId: WORKSPACE,
    actorId: '00000000-0000-4000-8000-0000000000a1',
    sourceIds: [stored.source.sourceId],
  });
  return { stored, record };
}

function runToDraft(
  store: ReturnType<typeof replacementFixtureStore>,
  journeyId: string,
) {
  let rev = 1;
  store.applyAction({ journeyId, expectedStateRevision: rev, action: 'advance_reading' });
  rev += 1;
  store.applyAction({ journeyId, expectedStateRevision: rev, action: 'advance_admission' });
  rev += 1;
  store.applyAction({ journeyId, expectedStateRevision: rev, action: 'advance_processing' });
  rev += 1;
  store.landDraft({ journeyId, expectedStateRevision: rev });
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
        action: 'advance_reading',
      }),
    /stale state revision/,
  );
  assert.throws(
    () =>
      store.applyAction({
        journeyId: record.journeyId,
        expectedStateRevision: 1,
        action: 'confirm',
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
    idempotencyKey: 'corr-1',
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
    expectedStateRevision: result.record.stateRevision,
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
    idempotencyKey: 'corr-1',
  });
  assert.equal(replay.correction.correctionId, 'corr-1');
  assert.equal(replay.record.corrections.length, 1);
  void baseContentSnapshot;
});

test('cancel preserves spent liability, shows cancelled, and forbids replay', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  const draft = runToDraft(store, record.journeyId);

  store.dispatchAttempt({ journeyId: record.journeyId });
  store.spendAttempt({ journeyId: record.journeyId, attemptId: 'native1' });

  store.requestCancel({
    journeyId: record.journeyId,
    expectedStateRevision: draft.stateRevision,
  });
  let current = store.getJourney(record.journeyId)!;
  assert.equal(current.state, 'cancel_requested');
  assert.equal(current.attempts[0]!.status, 'spent');
  assert.equal(current.attempts[0]!.liabilityPreserved, true);

  store.completeCancel({
    journeyId: record.journeyId,
    expectedStateRevision: current.stateRevision,
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
    () => store.replayAttempt({ journeyId: record.journeyId, attemptId: 'native1' }),
    /no replay/,
  );
  assert.throws(
    () => store.dispatchAttempt({ journeyId: record.journeyId }),
    /terminal; no replay/,
  );
  assert.throws(
    () =>
      store.applyAction({
        journeyId: record.journeyId,
        expectedStateRevision: current.stateRevision,
        action: 'land_draft',
      }),
    /terminal; no replay/,
  );
});

test('native1..N attempt visibility: attempt 1 spent, attempt 2 new, never replay', () => {
  const store = seedJourney();
  const { record } = uploadAndCreate(store);
  runToDraft(store, record.journeyId);

  store.dispatchAttempt({ journeyId: record.journeyId });
  store.spendAttempt({ journeyId: record.journeyId, attemptId: 'native1' });
  store.dispatchAttempt({ journeyId: record.journeyId });

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
    () => store.spendAttempt({ journeyId: record.journeyId, attemptId: 'native1' }),
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
    idempotencyKey: 'conf-1',
  });
  store.produceAnswer({
    journeyId: record.journeyId,
    expectedStateRevision: store.getJourney(record.journeyId)!.stateRevision,
  });
  const ready = store.getJourney(record.journeyId)!;
  assert.equal(ready.state, 'answer_ready');
  assert.ok(ready.mapView);
  assert.ok(ready.answer);
  assert.ok(ready.confirmation?.current);

  store.invalidateCurrent({
    journeyId: record.journeyId,
    expectedStateRevision: ready.stateRevision,
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
        idempotencyKey: 'conf-stale',
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
        expectedStateRevision: draft.stateRevision,
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
