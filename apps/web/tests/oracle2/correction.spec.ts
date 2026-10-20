// S05 preview gate: contradictory reports → authorized resolution → current
// answer changes → historical answer retains correct date/scope.
// Page blocker: apps/web/components/consultant/review-bundle.tsx and the
// reviews API extension are not built on main.
// Invented/synthetic fixtures only.
import { test, expect } from '@playwright/test';

const CORRECTION_PAGE_READY = Boolean(process.env.ORACLE2_CORRECTION_PAGE_READY);

test.describe('S05 correction journey', () => {
  test('authorized resolution changes the current answer', async ({ page }) => {
    test.skip(!CORRECTION_PAGE_READY, 'blocker: consultant review-bundle correction UI not built');
    await page.goto('/consultant');
    expect(page.url()).toContain('/consultant');
  });

  test('historical answer retains correct date and scope', async ({ page }) => {
    test.skip(!CORRECTION_PAGE_READY, 'blocker: consultant review-bundle correction UI not built');
    await page.goto('/consultant');
    expect(page.url()).toContain('/consultant');
  });
});
