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
  await expect(results.locator('tbody tr')).toHaveCount(5);
  await expect(results).toContainText('Where does licensing approval stall and why?');
  await expect(page.getByTestId('eval-form')).toBeVisible();
  await page.screenshot({ path: resolve(SHOTS, '05-eval-page.png'), fullPage: true });
});
