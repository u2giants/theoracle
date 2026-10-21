// S03 U3–U5 offline browser journey for the replacement endpoint family.
//
// Covers: correction → new revision (no body edit); control/cancel preserves
// liability and forbids replay; native1..N attempt visibility (attempt 1 spent,
// attempt 2 new); actual_native_pipeline_after_refresh (hostile case: browser
// uploads a real binary while the backend seeds an old model/graph-evidence
// result; after refresh the current native pipeline output must be shown and
// the seeded stale evidence must never be current).
//
// No skip stub. Invented/synthetic data only. Never company data, never a real
// provider. This Playwright run is offline browser-journey evidence for the
// replacement UI/API surface — it is NOT a native-acceptance proof path.
//
// How to run (local preview):
//   1. pnpm --filter @oracle/web dev          # or: pnpm dev
//   2. pnpm --filter @oracle/web exec playwright install chromium
//   3. pnpm --filter @oracle/web test:oracle2
//   Optional: ORACLE2_PREVIEW_URL=http://127.0.0.1:3000 (default localhost:3000)
// Run the dev server bound to 127.0.0.1, with explicit
// ORACLE2_REPLACEMENT_FIXTURE_MODE=1, ORACLE2_REPLACEMENT_TOKEN and a separate
// ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY (both at least 32 characters).
// Give the test process the same token and loopback ORACLE2_PREVIEW_URL.
// No readiness skip — a missing page/endpoint is a
// failure, which is the point of this spec.
import { test, expect, type Page } from '@playwright/test';

const PNG_BYTES_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

async function uploadOriginal(page: Page, opts?: { staleLabel?: string }): Promise<void> {
  if (opts?.staleLabel) {
    await page.getByTestId('stale-seeded-label').fill(opts.staleLabel);
  }
  const buffer = Buffer.from(PNG_BYTES_BASE64, 'base64');
  await page.getByTestId('replacement-upload').setInputFiles({
    name: 'invented-original.png',
    mimeType: 'image/png',
    buffer,
  });
  await expect(page.getByTestId('source-id')).toBeVisible();
}

async function createJourney(page: Page): Promise<void> {
  await page.getByTestId('create-journey-btn').click();
  await expect(page.getByTestId('journey-section')).toBeVisible();
}

async function advanceToDraft(page: Page): Promise<void> {
  await page.getByTestId('advance-reading-btn').click();
  await expect(page.getByTestId('current-state')).toContainText('awaiting_original_reading');
  await page.getByTestId('advance-admission-btn').click();
  await expect(page.getByTestId('current-state')).toContainText('awaiting_admission');
  await page.getByTestId('advance-processing-btn').click();
  await expect(page.getByTestId('current-state')).toContainText('processing');
  await page.getByTestId('land-draft-btn').click();
  await expect(page.getByTestId('current-state')).toContainText('draft_ready');
}

test.describe('replacement journey U3–U5 (offline fixture)', () => {
  test.beforeEach(async ({ page }) => {
    const token = process.env.ORACLE2_REPLACEMENT_TOKEN;
    if (!token) throw new Error('ORACLE2_REPLACEMENT_TOKEN required for local fixture login');
    await page.goto('/consultant/replacement');
    const status = await page.evaluate(async (fixtureToken) => {
      const denied = await fetch('/api/consultant/replacement/v1/session', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token: 'wrong-fixture-token' }),
      });
      if (denied.status !== 401) return denied.status;
      const response = await fetch('/api/consultant/replacement/v1/session', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token: fixtureToken }),
      });
      return response.status;
    }, token);
    expect(status).toBe(200);
    await page.goto('/consultant/replacement');
    await expect(page.getByTestId('replacement-workspace')).toBeVisible();
  });

  test('journey states render and transition through the State 13 machine', async ({ page }) => {
    // All State 13 literals render in the machine panel.
    for (const state of [
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
    ]) {
      await expect(page.getByTestId(`state-${state}`)).toBeVisible();
    }
    await expect(page.getByTestId('current-state')).toContainText('none');

    await uploadOriginal(page);
    await createJourney(page);
    await expect(page.getByTestId('current-state')).toContainText('uploading');

    await page.getByTestId('advance-reading-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('awaiting_original_reading');
    await page.getByTestId('advance-admission-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('awaiting_admission');
    await page.getByTestId('advance-processing-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('processing');
    await page.getByTestId('land-draft-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('draft_ready');
    await expect(page.getByTestId('map-workflow')).toContainText('wf-synthetic-intake');
    await expect(page.getByTestId('model-version')).toContainText('Version: 1');
  });

  test('correction produces a new revision without body edit', async ({ page }) => {
    await uploadOriginal(page);
    await createJourney(page);
    await advanceToDraft(page);

    // No model-body editor exists — correction is a connection request only.
    await expect(page.getByTestId('correction-panel')).toBeVisible();
    await expect(page.getByTestId('correction-reason')).toBeVisible();
    await expect(page.locator('textarea[data-testid="model-body-editor"]')).toHaveCount(0);

    await page.getByTestId('correction-reason').fill(
      'Record an explicit handoff owner after authorized review.',
    );
    await page.getByTestId('correct-btn').click();

    // Correction immediately places the journey in revision_pending and clears
    // current map/answer/badge (D0d). Old model is not served as current.
    await expect(page.getByTestId('current-state')).toContainText('revision_pending');
    await expect(page.getByTestId('map-absent')).toBeVisible();
    await expect(page.getByTestId('badge-absent')).toBeVisible();
    await expect(page.getByTestId('answer-absent')).toBeVisible();

    await page.getByTestId('land-revision-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('draft_ready');
    // Genuinely NEW revision: version 2 under the same artifact.
    await expect(page.getByTestId('model-version')).toContainText('Version: 2');
    await expect(page.getByTestId('correction-list')).toBeVisible();
    await expect(page.getByTestId('correction-revision')).toContainText('base v1 → new v2');
  });

  test('control/cancel preserves liability, shows cancelled, and forbids replay', async ({ page }) => {
    await uploadOriginal(page);
    await createJourney(page);
    await advanceToDraft(page);

    // Spend one native attempt so liability must be preserved across cancel.
    await page.getByTestId('dispatch-attempt-btn').click();
    await expect(page.getByTestId('attempt-native1-status')).toContainText('native1: new');
    await page.getByTestId('spend-native1').click();
    await expect(page.getByTestId('attempt-native1-status')).toContainText('native1: spent');

    await page.getByTestId('cancel-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('cancel_requested');
    await page.getByTestId('cancel-btn').click();
    await expect(page.getByTestId('current-state')).toContainText('cancelled');

    // Spent liability preserved — attempt remains visible and spent.
    await expect(page.getByTestId('attempt-native1-status')).toContainText('native1: spent');

    // Replay of a spent attempt is refused (no automatic retry).
    await page.getByTestId('replay-native1').click();
    await expect(page.getByTestId('error-banner')).toContainText('no replay');

    // No further promotion from a terminal state.
    await expect(page.getByTestId('land-draft-btn')).toBeDisabled();
  });

  test('native1..N attempt visibility: attempt 1 spent, attempt 2 new, never replay', async ({ page }) => {
    await uploadOriginal(page);
    await createJourney(page);
    await advanceToDraft(page);

    await page.getByTestId('dispatch-attempt-btn').click();
    await expect(page.getByTestId('attempt-native1')).toBeVisible();
    await page.getByTestId('spend-native1').click();
    await expect(page.getByTestId('attempt-native1-status')).toContainText('spent');

    await page.getByTestId('dispatch-attempt-btn').click();
    await expect(page.getByTestId('attempt-native2')).toBeVisible();
    await expect(page.getByTestId('attempt-native2-status')).toContainText('native2: new');

    // Attempt 2 is a NEW operation; replaying spent attempt 1 still refuses.
    await page.getByTestId('replay-native1').click();
    await expect(page.getByTestId('error-banner')).toContainText('no replay');
    // Attempt 1 stays spent — never resurrected to new.
    await expect(page.getByTestId('attempt-native1-status')).toContainText('native1: spent');
    await expect(page.getByTestId('attempt-native2-status')).toContainText('native2: new');
  });

  test('actual_native_pipeline_after_refresh: stale seed never wins; invalidation clears current', async ({ page }) => {
    // Hostile case (plan §10): browser uploads a real binary while the backend
    // seeds an old model/graph-evidence result.
    await uploadOriginal(page, { staleLabel: 'legacy-graph-evidence-v1' });
    await expect(page.getByTestId('stale-seeded-flag')).toContainText('yes');
    await createJourney(page);
    await advanceToDraft(page);

    // Current output is the native pipeline identity bound to the uploaded
    // original hash — not the seeded stale metadata.
    await expect(page.getByTestId('native-pipeline-output')).toContainText('native-fixture-v1');
    await expect(page.getByTestId('stale-seeded')).toBeVisible();
    await expect(page.getByTestId('stale-seeded')).toContainText('never current');

    const journeyId = await page.getByTestId('journey-section').innerText();
    expect(journeyId).toBeTruthy();

    // Simulated refresh: sessionStorage is restored from authoritative IDs.
    await page.reload();
    await expect(page.getByTestId('replacement-workspace')).toBeVisible();
    await expect(page.getByTestId('journey-section')).toBeVisible();
    await expect(page.getByTestId('current-state')).toContainText('draft_ready');
    // After refresh the current native pipeline output is still the live one.
    await expect(page.getByTestId('native-pipeline-output')).toContainText('native-fixture-v1');
    await expect(page.getByTestId('stale-seeded')).toContainText('never current');

    // Confirm + answer so there is a current map/answer/badge to clear.
    await page.getByTestId('confirm-btn').click();
    await expect(page.getByTestId('confirmed-badge')).toBeVisible();
    await page.getByTestId('ask-btn').click();
    await expect(page.getByTestId('answer-text')).toBeVisible();
    await expect(page.getByTestId('answer-text')).toContainText('Suggested improvements (not established fact)');
    await expect(page.getByTestId('map-workflow')).toBeVisible();

    // Actual invalidation: current map/answer/badge clear.
    await page.getByTestId('invalidate-btn').click();
    await expect(page.getByTestId('map-absent')).toBeVisible();
    await expect(page.getByTestId('answer-absent')).toBeVisible();
    await expect(page.getByTestId('badge-absent')).toBeVisible();

    // Refresh again: cleared state survives reload; stale seed still not current.
    await page.reload();
    await expect(page.getByTestId('map-absent')).toBeVisible();
    await expect(page.getByTestId('answer-absent')).toBeVisible();
    await expect(page.getByTestId('badge-absent')).toBeVisible();
    await expect(page.getByTestId('native-pipeline-output')).toContainText('native-fixture-v1');
    await expect(page.getByTestId('stale-seeded')).toContainText('never current');
  });

  test('original viewer serves PNG page parts from the fixture', async ({ page }) => {
    await uploadOriginal(page);
    const sourceId = (await page.getByTestId('source-id').innerText()).replace('Source: ', '').trim();
    expect(sourceId).toMatch(/^[0-9a-f-]{36}$/i);

    await page.goto(`/consultant/replacement/originals/${sourceId}/1`);
    await expect(page.getByTestId('original-viewer')).toBeVisible();
    await expect(page.getByTestId('original-page-image')).toBeVisible();
    const response = await page.request.get(
      `/api/consultant/replacement/v1/originals/${sourceId}/1`,
    );
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('image/png');
    expect(response.headers()['x-original-sha256']).toMatch(/^[a-f0-9]{64}$/);
  });

  test('unknown fields and unsupported intents fail closed', async ({ page }) => {
    const sourceResponse = await page.request.post(
      '/api/consultant/replacement/v1/sources',
      {
        headers: { origin: new URL(page.url()).origin },
        data: {
          bytesBase64: PNG_BYTES_BASE64,
          filename: 'invented.png',
          contentType: 'image/png',
          actorId: 'forged-actor',
        },
      },
    );
    // Unknown field 'actorId' is refused — body identities are ignored/rejected.
    expect(sourceResponse.status()).toBe(400);

    const createResponse = await page.request.post(
      '/api/consultant/replacement/v1/journeys',
      { headers: { origin: new URL(page.url()).origin }, data: { sourceIds: [], provider: 'forged' } },
    );
    expect(createResponse.status()).toBe(400);
  });
});
