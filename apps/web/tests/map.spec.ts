// Company Map page and source viewer (plan step 10 done-when).
// Opens the map, clicks the licensing community, clicks the Jessica node on
// the graph canvas, clicks a quote and lands on the transcript source with the
// quoted chunk highlighted. Screenshots go to tests/__screenshots__/map/.
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { e2eEnv, SEED_FILE, WEB_DIR } from './map/env';

type Seed = {
  transcript_id: string;
  jessica_id: string;
  jessica_name: string;
  licensing_community_id: string;
  eval_first_mean: number;
  eval_mean: number;
  interview_open: string;
  interview_answer: string;
  rec_licensing: string;
  rec_small: string;
  zh_entity_description: string;
  zh_community_title: string;
  zh_community_summary: string;
};

const SHOTS = resolve(WEB_DIR, 'tests', '__screenshots__', 'map');

function seed(): Seed {
  return JSON.parse(readFileSync(SEED_FILE, 'utf8')) as Seed;
}

async function signIn(context: BrowserContext): Promise<void> {
  const session = {
    access_token: e2eEnv.accessToken,
    token_type: 'bearer',
    expires_in: 3600 * 24 * 365,
    expires_at: Math.floor(Date.now() / 1000) + 3600 * 24 * 365,
    refresh_token: 'map-e2e-refresh-token',
    user: { id: e2eEnv.authUserId, aud: 'authenticated', email: 'map-e2e@test.invalid' },
  };
  const value = `base64-${Buffer.from(JSON.stringify(session)).toString('base64url')}`;
  await context.addCookies([
    {
      name: 'sb-localhost-auth-token',
      value,
      domain: 'localhost',
      path: '/',
      httpOnly: false,
      secure: false,
      sameSite: 'Lax',
    },
  ]);
}

async function nodePosition(page: Page, entityId: string): Promise<[number, number] | null> {
  const raw =
    (await page.getByTestId('community-graph').getAttribute('data-node-positions')) ?? '{}';
  return (JSON.parse(raw) as Record<string, [number, number]>)[entityId] ?? null;
}

async function clickGraphNode(page: Page, entityId: string): Promise<void> {
  // The dev server may hot-reload while screenshots are written, which
  // restarts the layout; wait until the node's position holds still.
  let settled: [number, number] | null = null;
  await expect
    .poll(
      async () => {
        const first = await nodePosition(page, entityId);
        await page.waitForTimeout(750);
        const second = await nodePosition(page, entityId);
        settled =
          first && second && first[0] === second[0] && first[1] === second[1] ? second : null;
        return settled !== null;
      },
      { timeout: 45_000 },
    )
    .toBe(true);
  const [x, y] = settled as unknown as [number, number];
  const canvas = page.locator('[data-testid="community-graph"] canvas').first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('graph canvas has no box');
  // Hover first: the graph picks the node under the pointer on its next
  // frame, then the click selects it (what a person's mouse does too).
  await page.mouse.move(box.x + x, box.y + y);
  await page.waitForTimeout(400);
  await page.mouse.click(box.x + x, box.y + y);
}

test('map → licensing community → Jessica → quote → highlighted transcript chunk', async ({
  page,
  context,
}) => {
  const ids = seed();
  await signIn(context);

  await page.goto('/map');
  const card = page.locator(
    `[data-testid="community-card"][data-community-id="${ids.licensing_community_id}"]`,
  );
  await expect(card).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('top-issues').locator('li').first()).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '01-map-home.png'), fullPage: true });

  await card.click();
  await expect(page.getByTestId('community-title')).toHaveText('Licensing approval');
  await expect(page.getByTestId('finding').first()).toBeVisible();
  await expect(page.getByTestId('stance-badge').first()).toBeVisible();
  await expect(page.getByTestId('source-chip').first()).toBeVisible();
  await expect(page.locator('[data-testid="community-graph"] canvas').first()).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '02-licensing-community.png'), fullPage: true });

  await clickGraphNode(page, ids.jessica_id);
  const drawer = page.getByTestId('entity-drawer');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByTestId('entity-name')).toHaveText(ids.jessica_name);
  await page.screenshot({ path: resolve(SHOTS, '03-jessica-drawer.png') });

  const quote = drawer.locator(
    `[data-testid="entity-quote"][data-source-id="${ids.transcript_id}"]`,
  );
  await expect(quote.first()).toBeVisible();
  const chunkId = await quote.first().getAttribute('data-chunk-id');
  expect(chunkId).toBeTruthy();
  await quote.first().click();

  await expect(page).toHaveURL(new RegExp(`/map/source/${ids.transcript_id}\\?chunk=${chunkId}`));
  await expect(page.getByTestId('source-title')).toContainText('teams-approval');
  const highlighted = page.locator(`[data-testid="source-chunk"][data-chunk-id="${chunkId}"]`);
  await expect(highlighted).toHaveAttribute('data-highlighted', 'true');
  await expect(highlighted).toBeInViewport();
  await expect(page.locator('[data-testid="source-chunk"][data-highlighted="true"]')).toHaveCount(
    1,
  );
  await page.screenshot({ path: resolve(SHOTS, '04-transcript-highlighted.png') });
});

// Plan step 11 done-when: the eval page shows a run on the fixture corpus.
test('eval page shows runs, the per-question table and the change since last run', async ({
  page,
  context,
}) => {
  const ids = seed();
  await signIn(context);
  await page.goto('/map/eval');
  const runs = page.getByTestId('eval-runs');
  await expect(runs).toBeVisible({ timeout: 60_000 });
  await expect(runs.locator('tbody tr')).toHaveCount(2);
  const pct = (value: number) => `${Math.round(value * 100)}%`;
  await expect(page.getByTestId('eval-mean').first()).toHaveText(pct(ids.eval_mean));
  await expect(page.getByTestId('eval-mean').nth(1)).toHaveText(pct(ids.eval_first_mean));
  const results = page.getByTestId('eval-results');
  await expect(results.locator('tbody tr')).toHaveCount(15);
  await expect(results).toContainText('Where does licensing approval stall and why?');
  await expect(page.getByTestId('eval-form')).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '05-eval-page.png'), fullPage: true });
});

// Plan step 12: the admin open-question page shows the queue, history, the
// reachable people with a pause switch, and the global switch.
test('open-question page shows queue, history and per-person pause', async ({ page, context }) => {
  const ids = seed();
  await signIn(context);
  await page.goto('/map/questions');
  const open = page.getByTestId('open-questions');
  await expect(open).toBeVisible({ timeout: 60_000 });
  await expect(open).toContainText(ids.interview_open);
  await expect(open).toContainText('nobody reachable yet');
  await expect(page.getByTestId('question-history')).toContainText(ids.interview_answer);
  await expect(page.getByTestId('interview-switch')).toContainText('Teams interviews: off');
  const people = page.getByTestId('interview-employees');
  await expect(people).toContainText('Map Test Admin');
  await page.screenshot({ path: resolve(SHOTS, '06-questions-page.png'), fullPage: true });
  await people.getByRole('button', { name: 'Pause' }).click();
  await expect(people.getByRole('button', { name: 'Resume' })).toBeVisible();
  await people.getByRole('button', { name: 'Resume' }).click();
  await expect(people.getByRole('button', { name: 'Pause' })).toBeVisible();
});

// Plan step 13: cards sorted by distinct sources; admin status buttons;
// Rejected hides the card.
test('recommendations page sorts by sources and hides rejected cards', async ({
  page,
  context,
}) => {
  const ids = seed();
  await signIn(context);
  await page.goto('/map/recommendations');
  const cards = page.getByTestId('recommendation');
  await expect(cards).toHaveCount(2, { timeout: 60_000 });
  await expect(cards.first()).toContainText(ids.rec_licensing);
  await expect(cards.first()).toContainText('The data is incomplete');
  await expect(cards.first().getByTestId('recommendation-options')).toContainText('No change');
  await page.screenshot({ path: resolve(SHOTS, '07-recommendations-page.png'), fullPage: true });
  await cards.first().getByRole('button', { name: 'Accept' }).click();
  await expect(cards.first().getByTestId('recommendation-status')).toContainText('accepted');
  await cards.nth(1).getByRole('button', { name: 'Reject' }).click();
  await expect(cards).toHaveCount(1);
  await expect(page.getByTestId('recommendations')).not.toContainText(ids.rec_small);
});

// Issue #255 review gate: the admin marks an entity and a relation wrong with
// notes, the flags survive a reload, and the review page lists and resolves them.
test('admin marks entity and relation wrong and resolves them on the review page', async ({
  page,
  context,
}) => {
  const ids = seed();
  await signIn(context);

  await page.goto(`/map/entity/${ids.jessica_id}`);
  await expect(page.getByTestId('entity-panel')).toBeVisible({ timeout: 60_000 });

  const entityFlag = page.locator('[data-testid="mark-wrong"][data-item-type="entity"]');
  await entityFlag.getByTestId('mark-wrong-button').click();
  await entityFlag.getByTestId('mark-wrong-note').fill('Wrong person on this account');
  await entityFlag.getByTestId('mark-wrong-save').click();
  await expect(entityFlag.getByTestId('mark-wrong-flagged')).toContainText(
    'Wrong person on this account',
  );

  const relationFlag = page
    .locator('[data-testid="mark-wrong"][data-item-type="relation"]')
    .first();
  await relationFlag.getByTestId('mark-wrong-button').click();
  await relationFlag.getByTestId('mark-wrong-note').fill('This hand-off is made up');
  await relationFlag.getByTestId('mark-wrong-save').click();
  await expect(relationFlag.getByTestId('mark-wrong-flagged')).toContainText(
    'This hand-off is made up',
  );

  await page.reload();
  await expect(page.getByTestId('entity-panel')).toBeVisible({ timeout: 60_000 });
  await expect(
    page
      .locator('[data-testid="mark-wrong"][data-item-type="entity"]')
      .getByTestId('mark-wrong-flagged'),
  ).toContainText('Wrong person on this account');
  await expect(
    page
      .locator('[data-testid="mark-wrong"][data-item-type="relation"]')
      .first()
      .getByTestId('mark-wrong-flagged'),
  ).toContainText('This hand-off is made up');
  await page.screenshot({ path: resolve(SHOTS, '08-entity-flagged.png'), fullPage: true });

  await page.goto(`/map/community/${ids.licensing_community_id}`);
  await expect(page.getByTestId('community-title')).toBeVisible({ timeout: 60_000 });
  await expect(
    page.locator('[data-testid="mark-wrong"][data-item-type="community"]'),
  ).toBeVisible();
  await page.locator('details[data-testid="graph-links"] summary').click();
  await page.getByTestId('graph-link').first().click();
  const detail = page.getByTestId('relation-detail');
  await expect(detail).toBeVisible();
  await expect(
    detail.locator('[data-testid="mark-wrong"][data-item-type="relation"]'),
  ).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '09-relation-detail.png'), fullPage: true });

  await page.goto('/map/review');
  const rows = page.getByTestId('review-flag');
  await expect(rows).toHaveCount(2, { timeout: 60_000 });
  await expect(
    page.getByTestId('review-note').filter({ hasText: 'Wrong person on this account' }),
  ).toBeVisible();
  await expect(
    page.getByTestId('review-note').filter({ hasText: 'This hand-off is made up' }),
  ).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '10-review-flags.png'), fullPage: true });

  await rows
    .filter({ hasText: 'Wrong person on this account' })
    .getByTestId('review-resolve')
    .click();
  await expect(rows).toHaveCount(1);
  await expect(page.getByTestId('review-note')).toContainText('This hand-off is made up');
  await page.screenshot({ path: resolve(SHOTS, '11-review-resolved.png'), fullPage: true });
});

test('zh locale shows translations and keeps chrome English', async ({ page, context }) => {
  const ids = seed();
  await signIn(context);

  // The admin Language dropdown puts this employee in the China group.
  await page.goto('/admin/employees');
  const localeSelect = page.locator('select[name="locale"]').first();
  await expect(localeSelect).toBeVisible({ timeout: 60_000 });
  await localeSelect.selectOption('zh-CN');
  // The form submits on change; wait for the server action to confirm.
  await expect(page.getByText('Saved.').first()).toBeVisible({ timeout: 30_000 });

  await page.goto(`/map/community/${ids.licensing_community_id}`);
  await expect(page.getByTestId('community-title')).toHaveText(ids.zh_community_title, {
    timeout: 60_000,
  });
  await expect(page.getByText(ids.zh_community_summary)).toBeVisible();
  // Chrome stays English.
  await expect(page.getByText('← Company Map')).toBeVisible();
  await expect(page.getByText('Findings')).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '12-zh-community.png'), fullPage: true });

  await page.goto(`/map/entity/${ids.jessica_id}`);
  await expect(page.getByText(ids.zh_entity_description)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('← Company Map')).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '13-zh-entity.png'), fullPage: true });

  // Back to English for any later run sharing the database.
  await page.goto('/admin/employees');
  await page.locator('select[name="locale"]').first().selectOption('en');
  await expect(page.getByText('Saved.').first()).toBeVisible({ timeout: 30_000 });
});

// Repair plan B1: the owner-approved question set. Admin sees a draft
// question with its recommendation, approves it, and the question now counts
// toward the eval bar; the abstention draft keeps its badge and its draft
// status. Times shown to humans are New York (EST/EDT).
test('admin approves a draft eval question and it counts', async ({ page, context }) => {
  await signIn(context);
  await page.goto('/map/eval');
  const draft = page
    .getByTestId('eval-question')
    .filter({ hasText: 'How long does the internal artwork review take in the procedure?' });
  await expect(draft).toHaveCount(1, { timeout: 60_000 });
  await expect(draft).toHaveAttribute('data-status', 'draft');
  await expect(draft.getByTestId('question-status')).toContainText(
    'does not count toward the eval bar yet',
  );
  await expect(draft.getByTestId('question-recommendation')).toContainText(
    'Approve as written.',
  );
  await page.screenshot({ path: resolve(SHOTS, '14-eval-draft-question.png'), fullPage: true });

  await draft.getByTestId('question-approve').click();
  await expect(draft).toHaveAttribute('data-status', 'approved');
  await expect(draft.getByTestId('question-status')).toContainText('EST');
  await expect(draft.getByTestId('question-status')).toContainText(
    'counts toward the eval bar',
  );
  await expect(draft.getByTestId('question-approve')).toHaveCount(0);

  const abstention = page
    .getByTestId('eval-question')
    .filter({ hasText: 'How many artwork reviews did the licensing team complete last quarter?' });
  await expect(abstention).toHaveCount(1);
  await expect(abstention).toHaveAttribute('data-status', 'draft');
  await expect(abstention.getByTestId('question-abstention')).toContainText(
    'The documents do not say',
  );
  await page.screenshot({ path: resolve(SHOTS, '15-eval-approved-question.png'), fullPage: true });
});
