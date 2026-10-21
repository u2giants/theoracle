import { test, expect } from '@playwright/test';

const sourceId = process.env.ORACLE2_HOLISTIC_FIXTURE_SOURCE_ID;
const draftId = process.env.ORACLE2_HOLISTIC_FIXTURE_DRAFT_ID;
const token = process.env.ORACLE2_PILOT_TOKEN ?? 'synthetic-browser-token';
const sourceIds = JSON.parse(process.env.ORACLE2_HOLISTIC_FIXTURE_SOURCE_IDS ?? '[]') as string[];

test.describe('synthetic holistic connected answer', () => {
  test.beforeEach(async ({ page }) => {
    if (!sourceId || !draftId || sourceIds.length !== 2) {
      test.skip(true, 'holistic browser fixture environment is required');
    }
    await page.addInitScript(({ source, draft }) => {
      sessionStorage.setItem('oracle2-source-id', source);
      sessionStorage.setItem('oracle2-draft-id', draft);
    }, { source: sourceId!, draft: draftId! });
    await page.goto('/consultant');
    const denied = await page.evaluate(async () => {
      const missing = await fetch('/api/consultant/questions', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'content-type': 'application/json' }, body: '{}',
      });
      const wrong = await fetch('/api/consultant/session', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token: 'invented-invalid-holistic-token' }),
      });
      return { missing: missing.status, wrong: wrong.status };
    });
    expect(denied).toEqual({ missing: 401, wrong: 401 });
    await page.getByTestId('pilot-token').fill(token);
    await page.getByTestId('pilot-login-btn').click();
    await expect(page.getByTestId('pilot-actor')).toBeVisible();
    const cookie = (await page.context().cookies()).find((entry) => entry.name === 'oracle2_pilot_session');
    expect(cookie?.secure).toBe(true);
  });

  test('dispatches opaque question and renders two-source holistic evidence', async ({ page }) => {
    const response = await page.evaluate(async (data) => {
      const result = await fetch('/api/consultant/questions', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'content-type': 'application/json' }, body: JSON.stringify(data),
      });
      return { status: result.status, receipt: await result.json() };
    }, {
        question: 'How does intake hand off to review, including the incomplete-packet exception?',
        sourceId,
        draftId,
    });
    expect(response.status).toBe(202);
    const receipt = response.receipt;
    expect(receipt.runId).toMatch(/^[0-9a-f-]{36}$/i);

    await page.evaluate((runId) => sessionStorage.setItem('oracle2-run-id', runId), receipt.runId);
    await page.reload();
    await expect(page.getByTestId('answer-section')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('answer-method')).toContainText('2 original documents');
    await expect(page.getByTestId('answer-text')).toContainText('incomplete packets return');
    await expect(page.getByTestId('answer-text')).toContainText('Unknown or missing evidence');
    const citations = page.getByTestId(/^citation-/);
    await expect(citations).toHaveCount(2);
    await expect(citations.nth(0)).toContainText('Intake Lead sends the packet');
    await expect(citations.nth(1)).toContainText('packet is incomplete');
  });
});
