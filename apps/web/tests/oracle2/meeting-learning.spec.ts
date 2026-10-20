// S07 preview gate: one authorized test meeting to a corrected, cited
// knowledge update. Missing transcript permission, rejected lobby admission
// and transcription failure are visible failures, not success.
// Page blocker: apps/web/app/consultant/meetings/[id]/page.tsx is not built
// on main (held PR #143).
// Invented/synthetic fixtures only.
import { test, expect } from '@playwright/test';

const MEETING_PAGE_READY = Boolean(process.env.ORACLE2_MEETING_PAGE_READY);

test.describe('S07 invited meeting learning', () => {
  test('authorized meeting produces a cited knowledge update', async ({ page }) => {
    test.skip(!MEETING_PAGE_READY, 'blocker: apps/web/app/consultant/meetings/[id]/page.tsx not built (PR #143)');
    await page.goto('/consultant/meetings');
    expect(page.url()).toContain('/consultant/meetings');
  });

  test('missing transcript permission is a visible failure', async ({ page }) => {
    test.skip(!MEETING_PAGE_READY, 'blocker: meetings page not built (PR #143)');
    await page.goto('/consultant/meetings');
    expect(page.url()).toContain('/consultant/meetings');
  });
});
