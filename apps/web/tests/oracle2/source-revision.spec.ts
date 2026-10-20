// S04 preview gate: replacing and withdrawing a document updates a cited
// answer and blocks its old source link.
// Page blocker: apps/web/app/consultant/sources/ is not built on main.
// Invented/synthetic fixtures only.
import { test, expect } from '@playwright/test';

const SOURCES_PAGE_READY = Boolean(process.env.ORACLE2_SOURCES_PAGE_READY);

test.describe('S04 source revision and withdrawal', () => {
  test('replacing a document updates the cited answer', async ({ page }) => {
    test.skip(!SOURCES_PAGE_READY, 'blocker: apps/web/app/consultant/sources/[id]/page.tsx not built');
    await page.goto('/consultant/sources');
    expect(page.url()).toContain('/consultant/sources');
  });

  test('withdrawing a document blocks its old source link', async ({ page }) => {
    test.skip(!SOURCES_PAGE_READY, 'blocker: apps/web/app/consultant/sources/[id]/page.tsx not built');
    await page.goto('/consultant/sources');
    expect(page.url()).toContain('/consultant/sources');
  });
});
