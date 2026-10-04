// S03 pilot journey browser test: login → upload → correct → confirm → answer after refresh.
import { test, expect } from '@playwright/test';

const PROCESS_DOC = [
  'step_id | owner | action | handoff_to | exception',
  '1 | Designer | Submit product concept for licensing review | Licensing | —',
  '2 | Licensing | Review concept against brand guidelines within 5 business days | Production planning | New material requires environmental compliance sign-off before handoff',
  '3 | Production planning | Schedule the manufacturing run | Manufacturing | —',
].join('\n');

async function pilotLogin(page: import('@playwright/test').Page) {
  const token = process.env.ORACLE2_PILOT_TOKEN ?? 'test-pilot-token';
  await page.goto('/consultant');
  const tokenBox = page.getByTestId('pilot-token');
  await tokenBox.click();
  await tokenBox.pressSequentially(token, { delay: 15 });
  await expect(tokenBox).toHaveValue(token);
  await page.getByTestId('pilot-login-btn').click();
  await expect(page.getByTestId('pilot-actor')).toBeVisible({ timeout: 10_000 });
}

test.describe('S03 pilot journey', () => {
  test('login → upload → correction → confirmation → answer after page refresh', async ({ page }) => {
    await pilotLogin(page);

    // 1. Upload the process table (each row is its own block).
    await page.getByTestId('document-text').fill(PROCESS_DOC);
    await page.getByTestId('upload-btn').click();
    await expect(page.getByTestId('source-id')).toBeVisible();
    await expect(page.getByTestId('block-0')).toBeVisible();
    await expect(page.getByTestId('block-1')).toBeVisible();
    await expect(page.getByTestId('draft-status')).toContainText('draft');

    // 2. Correct one connection (change the from/to step) and prove it is cited.
    await page.getByTestId('conn-from').selectOption('0');
    await page.getByTestId('conn-to').selectOption('2');
    await page.getByTestId('correct-btn').click();
    await expect(page.getByTestId('draft-status')).toContainText('corrected');

    // 3. Confirm the scoped draft.
    await page.getByTestId('confirm-btn').click();
    await expect(page.getByTestId('draft-status')).toContainText('confirmed');

    // 4. Ask a connected question — answer must include the corrected edge.
    await page.getByTestId('question-input').fill(
      'Where can the handoff between licensing and production fail?',
    );
    await page.getByTestId('ask-btn').click();
    await expect(page.getByTestId('answer-section')).toBeVisible();
    await expect(page.getByTestId('answer-text')).not.toBeEmpty();
    await expect(page.getByTestId('answer-text')).toContainText('Process-map connections');
    await expect(page.getByTestId('answer-text')).toContainText('0→2');
    await expect(page.getByTestId('answer-text')).toContainText(/Connected process step|Process-map context only/);
    await expect(page.getByTestId('citations')).toBeVisible();
    await expect(page.getByTestId('hypothetical')).toBeVisible();
    await expect(page.getByTestId('hypothetical')).toContainText('not established fact');

    // 5. Page refresh — the answer is still retrievable via session.
    await page.reload();
    await expect(page.getByTestId('answer-section')).toBeVisible();
    await expect(page.getByTestId('answer-text')).not.toBeEmpty();
    await expect(page.getByTestId('citations')).toBeVisible();
  });

  test('upload shows missing evidence for unrelated question', async ({ page }) => {
    await pilotLogin(page);
    await page.getByTestId('document-text').fill('The weather is pleasant today.');
    await page.getByTestId('upload-btn').click();
    await expect(page.getByTestId('source-id')).toBeVisible();
    await page.getByTestId('confirm-btn').click();
    await expect(page.getByTestId('draft-status')).toContainText('confirmed');
    await page.getByTestId('question-input').fill('What is the licensing approval threshold?');
    await page.getByTestId('ask-btn').click();
    await expect(page.getByTestId('answer-text')).toContainText('No source evidence');
    await expect(page.getByTestId('hypothetical')).not.toBeVisible();
  });

  test('mutating APIs refuse missing session', async ({ request }) => {
    const noAuth = await request.post('/api/consultant/sources', {
      data: { text: 'Step 1: test', filename: 'x.txt' },
    });
    expect(noAuth.status()).toBe(401);
  });

  test('session refuses invalid pilot token', async ({ request }) => {
    const bad = await request.post('/api/consultant/session', {
      data: { token: 'not-the-token' },
    });
    expect(bad.status()).toBe(401);
  });

  test('store-backed authority fails closed without ORACLE2_DATABASE_URL', async () => {
    const prevDb = process.env.ORACLE2_DATABASE_URL;
    const prevToken = process.env.ORACLE2_PILOT_TOKEN;
    const prevActor = process.env.ORACLE2_PILOT_ACTOR;
    delete process.env.ORACLE2_DATABASE_URL;
    process.env.ORACLE2_PILOT_TOKEN = 'unit-test-token';
    process.env.ORACLE2_PILOT_ACTOR = 'pilot-user';
    try {
      const auth = await import('../../lib/oracle2-pilot-auth');
      const authority = await import('../../lib/oracle2-authority');
      expect(await authority.hasAuthority('pilot-user', 'confirm')).toBe(false);
      const created = await auth.createSession('unit-test-token');
      expect(created.ok).toBe(false);
      if (!created.ok) {
        expect(created.status).toBe(403);
      }
    } finally {
      if (prevDb === undefined) delete process.env.ORACLE2_DATABASE_URL;
      else process.env.ORACLE2_DATABASE_URL = prevDb;
      if (prevToken === undefined) delete process.env.ORACLE2_PILOT_TOKEN;
      else process.env.ORACLE2_PILOT_TOKEN = prevToken;
      if (prevActor === undefined) delete process.env.ORACLE2_PILOT_ACTOR;
      else process.env.ORACLE2_PILOT_ACTOR = prevActor;
    }
  });
});
