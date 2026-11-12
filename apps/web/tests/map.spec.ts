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
  contradiction_summary: string;
  contradiction_timeline_summary: string;
  contradiction_entity_id: string;
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

  // G1: resolve requires choosing an action first, then the write creates a
  // correction keyed by content.
  await expect(
    rows.filter({ hasText: 'Wrong person on this account' }).getByTestId('review-resolve'),
  ).toBeDisabled();
  await rows
    .filter({ hasText: 'Wrong person on this account' })
    .getByTestId('review-action')
    .selectOption('reject');
  await page.screenshot({ path: resolve(SHOTS, '18-review-resolve-action.png'), fullPage: true });
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

// Repair plan B4: the admin health panel on /map/sources surfaces a seeded
// failed job with its error text (nothing falls back silently).
const B4_SEED_ERROR = 'B4 seeded failure: provider returned 503';

async function b4SeedFailedJob(seed: boolean): Promise<void> {
  const { execFileSync } = await import('node:child_process');
  const brainDir = resolve(WEB_DIR, '..', 'brain');
  const script = seed
    ? "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      "conn.execute(\"DELETE FROM cmap.job WHERE error LIKE 'B4 seeded%'\"); " +
      `conn.execute("INSERT INTO cmap.job (kind, payload, state, attempts, error) VALUES ` +
      `('read_source', '{\\"source_id\\": \\"99999999-9999-4999-8999-999999999999\\"}'::jsonb, ` +
      `'failed', 3, '${B4_SEED_ERROR}')"); conn.commit(); conn.close()`
    : "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      "conn.execute(\"DELETE FROM cmap.job WHERE error LIKE 'B4 seeded%'\"); " +
      'conn.commit(); conn.close()';
  execFileSync('uv', ['run', 'python', '-c', script], {
    cwd: brainDir,
    env: {
      ...process.env,
      DATABASE_URL: e2eEnv.databaseUrl,
      FALKORDB_URL: e2eEnv.falkordbUrl,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  });
}

test('health panel shows the seeded failed job with its error text', async ({ page, context }) => {
  await b4SeedFailedJob(true);
  try {
    await signIn(context);
    await page.goto('/map/sources');
    const panel = page.getByTestId('health-panel');
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('health-sources-by-state')).toBeVisible();
    await expect(page.getByTestId('health-last-build')).toBeVisible();
    await expect(page.getByTestId('health-spend-today')).toBeVisible();
    const failedJob = page
      .getByTestId('health-job')
      .filter({ hasText: B4_SEED_ERROR });
    await expect(failedJob).toHaveCount(1);
    await expect(failedJob.getByTestId('health-job-error')).toHaveText(B4_SEED_ERROR);
    await expect(page.getByTestId('health-failed-extractions')).toBeVisible();
    await page.screenshot({ path: resolve(SHOTS, '14-health-panel.png'), fullPage: true });
  } finally {
    await b4SeedFailedJob(false);
  }
});

// Repair plan C1: the curated business-function list. The page renders the
// 13 seeded functions with their aliases and the admin rename/merge/add/
// retire controls. Times shown to humans are New York (EST/EDT); this page
// shows none.
test('functions page renders the curated function list', async ({ page, context }) => {
  await signIn(context);
  await page.goto('/map/functions');
  const rows = page.getByTestId('function-row');
  await expect(rows).toHaveCount(13, { timeout: 60_000 });
  const sales = rows.filter({ has: page.getByTestId('function-key').filter({ hasText: 'sales-customer-accounts' }) });
  await expect(sales.getByTestId('function-name')).toHaveText('Sales & Customer Accounts');
  await expect(sales.getByTestId('function-aliases')).toContainText('Sales Team');
  const licensing = rows.filter({ has: page.getByTestId('function-key').filter({ hasText: /^licensing$/ }) });
  await expect(licensing.getByTestId('function-aliases')).toContainText('Licensing Team');
  await expect(rows.filter({ has: page.getByTestId('function-key').filter({ hasText: 'sampling' }) }).getByTestId('function-name')).toHaveText('Sampling');
  // Admin (the e2e employee) sees the edit, merge, retire and add controls.
  await expect(page.getByTestId('function-edit')).toHaveCount(13);
  await expect(page.getByTestId('function-retire')).toHaveCount(13);
  await expect(page.getByTestId('function-merge-submit')).toHaveCount(13);
  await expect(page.getByTestId('functions-add-form')).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '16-functions-list.png'), fullPage: true });
});

// Repair plan D1: the source page shows the effective date and where it
// came from. The seeded transcript is the teams-approval-2026-03-14 meeting.
test('source page shows the effective date and its origin', async ({ page, context }) => {
  const ids = seed();
  await signIn(context);
  await page.goto(`/map/source/${ids.transcript_id}`);
  const date = page.getByTestId('source-date');
  await expect(date).toBeVisible({ timeout: 60_000 });
  await expect(date).toContainText('effective 2026-03-14');
  await expect(date).toContainText('meeting start');
  await page.screenshot({ path: resolve(SHOTS, '17-source-date.png') });
});

// Repair plan C2: the function assignment control on the source and entity
// pages. Seeded rows show weight and origin (auto = the assignment job,
// admin = set here and never overwritten by a re-run — the re-run contract is
// proven in apps/brain/tests/test_functions.py). Times shown to humans are
// New York (EST/EDT); this control shows none.
async function c2SeedAssignments(assign: boolean): Promise<void> {
  const { execFileSync } = await import('node:child_process');
  const brainDir = resolve(WEB_DIR, '..', 'brain');
  const { jessica_id, transcript_id } = seed();
  const wipe =
    `conn.execute("DELETE FROM cmap.source_function WHERE source_id = '${transcript_id}'"); ` +
    `conn.execute("DELETE FROM cmap.entity_function WHERE entity_id = '${jessica_id}'"); `;
  const script = assign
    ? "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      wipe +
      `conn.execute("INSERT INTO cmap.source_function (source_id, function_id, weight, origin) ` +
      `SELECT '${transcript_id}', id, 0.8, 'auto' FROM cmap.function WHERE key = 'licensing'"); ` +
      `conn.execute("INSERT INTO cmap.entity_function (entity_id, function_id, weight, origin) ` +
      `SELECT '${jessica_id}', id, 0.9, 'admin' FROM cmap.function WHERE key = 'licensing'"); ` +
      `conn.execute("INSERT INTO cmap.entity_function (entity_id, function_id, weight, origin) ` +
      `SELECT '${jessica_id}', id, 0.4, 'auto' FROM cmap.function WHERE key = 'sampling'"); ` +
      'conn.commit(); conn.close()'
    : "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      wipe +
      'conn.commit(); conn.close()';
  execFileSync('uv', ['run', 'python', '-c', script], {
    cwd: brainDir,
    env: {
      ...process.env,
      DATABASE_URL: e2eEnv.databaseUrl,
      FALKORDB_URL: e2eEnv.falkordbUrl,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  });
}

test('entity and source pages show function assignments and the admin sets one', async ({
  page,
  context,
}) => {
  await c2SeedAssignments(true);
  try {
    await signIn(context);
    const { jessica_id, transcript_id } = seed();
    await page.goto(`/map/entity/${jessica_id}`);
    const control = page.getByTestId('function-assign');
    await expect(control).toBeVisible({ timeout: 60_000 });
    const licensingRow = control
      .getByTestId('function-assign-row')
      .filter({ hasText: 'Licensing' });
    await expect(licensingRow).toHaveCount(1);
    await expect(licensingRow.getByTestId('function-assign-origin')).toHaveText('admin');
    const samplingRow = control
      .getByTestId('function-assign-row')
      .filter({ hasText: 'Sampling' });
    await expect(samplingRow).toHaveCount(1);
    await expect(samplingRow.getByTestId('function-assign-origin')).toHaveText('auto');

    const designOption = control
      .getByTestId('function-assign-option')
      .filter({ hasText: 'Product Design & Development' });
    await designOption.getByTestId('function-assign-check').check();
    await designOption.getByTestId('function-assign-weight').fill('0.6');
    await control.getByTestId('function-assign-save').click();
    await expect(control.getByTestId('function-assign-message')).toHaveText('Saved.');
    const designRow = control
      .getByTestId('function-assign-row')
      .filter({ hasText: 'Product Design & Development' });
    await expect(designRow).toHaveCount(1);
    await expect(designRow.getByTestId('function-assign-origin')).toHaveText('admin');
    await expect(licensingRow).toHaveCount(1); // the seeded admin row survived the save
    await page.screenshot({ path: resolve(SHOTS, '17-function-assignment.png'), fullPage: true });

    await page.goto(`/map/source/${transcript_id}`);
    const sourceControl = page.getByTestId('function-assign');
    await expect(sourceControl).toBeVisible({ timeout: 60_000 });
    await expect(
      sourceControl.getByTestId('function-assign-row').filter({ hasText: 'Licensing' }),
    ).toHaveCount(1);
  } finally {
    await c2SeedAssignments(false);
  }
});

// Repair plan D2: source supersession on the sources page. A proposed
// "newer version of X" (cmap.source_version row with decided_at NULL) shows
// with a one-click confirm; confirming stamps it decided and the row then
// shows its supersession state. Times shown to humans are New York
// (EST/EDT); this page shows none.
const D2_OLD_ID = '00000000-0000-4000-8000-0000000000d1';
const D2_NEW_ID = '00000000-0000-4000-8000-0000000000d2';

async function d2SeedVersions(seed: boolean): Promise<void> {
  const { execFileSync } = await import('node:child_process');
  const brainDir = resolve(WEB_DIR, '..', 'brain');
  const wipe = `conn.execute("DELETE FROM cmap.source WHERE id IN ('${D2_OLD_ID}', '${D2_NEW_ID}')"); `;
  const script = seed
    ? "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      wipe +
      `conn.execute("INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes, ` +
      `effective_date, date_origin) VALUES ('${D2_OLD_ID}', 'text', 'Widget Policy (D2)', ` +
      `'test/d2-old.txt', 'd2-e2e-old-sha', 10, '2025-01-15', 'admin'), ('${D2_NEW_ID}', 'text', ` +
      `'Widget Policy (D2)', 'test/d2-new.txt', 'd2-e2e-new-sha', 11, '2025-06-01', 'admin')"); ` +
      `conn.execute("INSERT INTO cmap.source_version (source_id, supersedes_source_id, origin, ` +
      `decided_at) VALUES ('${D2_NEW_ID}', '${D2_OLD_ID}', 'auto_similarity', NULL)"); ` +
      'conn.commit(); conn.close()'
    : "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      wipe +
      'conn.commit(); conn.close()';
  execFileSync('uv', ['run', 'python', '-c', script], {
    cwd: brainDir,
    env: {
      ...process.env,
      DATABASE_URL: e2eEnv.databaseUrl,
      FALKORDB_URL: e2eEnv.falkordbUrl,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  });
}

test('sources page shows a newer-version proposal and the one-click confirm', async ({
  page,
  context,
}) => {
  await d2SeedVersions(true);
  try {
    await signIn(context);
    await page.goto('/map/sources');
    const proposal = page
      .getByTestId('source-version')
      .filter({ hasText: 'Newer version proposed' });
    await expect(proposal).toHaveCount(1, { timeout: 60_000 });
    await expect(proposal).toContainText('Widget Policy (D2)');
    await proposal.getByTestId('source-version-confirm').click();
    const decided = page.getByTestId('source-version').filter({ hasText: 'Superseded by' });
    await expect(decided).toHaveCount(1, { timeout: 60_000 });
    await expect(
      page.getByTestId('source-supersedes').filter({ hasText: 'Supersedes' }),
    ).toHaveCount(1);
    await page.screenshot({ path: resolve(SHOTS, '19-source-versions.png'), fullPage: true });
  } finally {
    await d2SeedVersions(false);
  }
});

// Repair plan G2: the admin merge flow on the entity page. Two throwaway
// Person entities are seeded straight into the e2e database; the admin merges
// one into the other through the entity picker, and the destination then
// shows the moved mention. Times shown to humans are New York (EST/EDT);
// this flow shows none.
const G2_SRC_ID = '00000000-0000-4000-8000-0000000000f3';
const G2_CHUNK_ID = '00000000-0000-4000-8000-0000000000f4';
const G2_A_ID = '00000000-0000-4000-8000-0000000000f1';
const G2_B_ID = '00000000-0000-4000-8000-0000000000f2';

async function g2SeedMerge(seed: boolean): Promise<void> {
  const { execFileSync } = await import('node:child_process');
  const brainDir = resolve(WEB_DIR, '..', 'brain');
  const wipe =
    `conn.execute("DELETE FROM cmap.source WHERE id = '${G2_SRC_ID}'"); ` +
    `conn.execute("DELETE FROM cmap.entity WHERE id IN ('${G2_A_ID}', '${G2_B_ID}')"); ` +
    "conn.execute(\"DELETE FROM cmap.correction WHERE target_key LIKE '%tester%'\"); ";
  const script = seed
    ? "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      wipe +
      `conn.execute("INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes) ` +
      `VALUES ('${G2_SRC_ID}', 'text', 'Widget Tester notes', 'test/g2-merge.txt', ` +
      `'g2-e2e-merge-sha', 12)"); ` +
      `conn.execute("INSERT INTO cmap.chunk (id, source_id, ordinal, locator, text, token_count) ` +
      `VALUES ('${G2_CHUNK_ID}', '${G2_SRC_ID}', 0, '{}'::jsonb, ` +
      `'Widget Tester was mentioned. W. Tester was mentioned.', 8)"); ` +
      `conn.execute("INSERT INTO cmap.entity (id, entity_type, canonical_name, ` +
      `mention_count, source_count) VALUES ('${G2_A_ID}', 'Person', 'Widget Tester', 1, 1), ` +
      `('${G2_B_ID}', 'Person', 'W. Tester', 1, 1)"); ` +
      `conn.execute("INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, ` +
      `normalized_name, quote, entity_id) VALUES ('${G2_CHUNK_ID}', 'Person', ` +
      `'Widget Tester', 'widget tester', 'Widget Tester was mentioned.', '${G2_A_ID}'), ` +
      `('${G2_CHUNK_ID}', 'Person', 'W. Tester', 'w tester', 'W. Tester was mentioned.', ` +
      `'${G2_B_ID}')"); ` +
      'conn.commit(); conn.close()'
    : "import os, psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); " +
      wipe +
      'conn.commit(); conn.close()';
  execFileSync('uv', ['run', 'python', '-c', script], {
    cwd: brainDir,
    env: {
      ...process.env,
      DATABASE_URL: e2eEnv.databaseUrl,
      FALKORDB_URL: e2eEnv.falkordbUrl,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'inherit'],
  });
}

test('entity page admin merge flow merges one entity into another', async ({
  page,
  context,
}) => {
  await g2SeedMerge(true);
  try {
    await signIn(context);
    await page.goto(`/map/entity/${G2_A_ID}`);
    const panel = page.getByTestId('entity-panel');
    await expect(panel).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('entity-name')).toHaveText('Widget Tester');
    const admin = page.getByTestId('entity-admin');
    await expect(admin).toBeVisible();

    await admin.getByTestId('entity-admin-merge-open').click();
    const picker = admin.getByTestId('entity-admin-merge-picker');
    await picker.getByTestId('entity-picker-input').fill('Tester');
    const option = picker
      .getByTestId('entity-picker-option')
      .filter({ hasText: 'W. Tester' });
    await expect(option).toHaveCount(1, { timeout: 30_000 });
    await option.click();
    await admin.getByTestId('entity-admin-merge-confirm').click();
    await expect(admin.getByTestId('entity-admin-message')).toContainText(
      'Merged into W. Tester',
      { timeout: 30_000 },
    );
    await page.screenshot({ path: resolve(SHOTS, '20-entity-merge.png'), fullPage: true });

    await page.goto(`/map/entity/${G2_B_ID}`);
    await expect(page.getByTestId('entity-name')).toHaveText('W. Tester');
    await expect(page.getByTestId('entity-panel')).toContainText(
      'Widget Tester was mentioned',
      { timeout: 30_000 },
    );
  } finally {
    await g2SeedMerge(false);
  }
});

// Repair plan D3: the contradictions page lists open conflicts and the
// recorded timeline changes, and both entities show the disagreement.
test('contradictions page and entity section show the sources disagree', async ({
  page,
  context,
}) => {
  await signIn(context);
  await page.goto('/map/contradictions');
  await expect(page.getByTestId('contradictions-page')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('contradiction-row')).toHaveCount(2);
  await expect(
    page
      .getByTestId('contradiction-summary')
      .filter({ hasText: seed().contradiction_summary }),
  ).toBeVisible();
  await expect(page.getByText(seed().contradiction_timeline_summary)).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '21-contradictions.png'), fullPage: true });

  await page.goto(`/map/entity/${seed().contradiction_entity_id}`);
  const panel = page.getByTestId('entity-panel');
  await expect(panel).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('entity-contradiction')).toHaveCount(2);
  await expect(
    page
      .getByTestId('entity-contradiction-summary')
      .filter({ hasText: seed().contradiction_summary }),
  ).toBeVisible();
});
