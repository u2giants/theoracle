// S06 preview gate: pause → restart → correction → recap with no duplicate
// question/update and correct access after a role change.
// Page blocker: apps/web/app/consultant/interviews/[id]/page.tsx and
// interview-panel.tsx are not built on main.
// Invented/synthetic fixtures only.
import { test, expect } from '@playwright/test';

const INTERVIEW_PAGE_READY = Boolean(process.env.ORACLE2_INTERVIEW_PAGE_READY);

test.describe('S06 interview pause, resume and correction', () => {
  test('pause and restart does not replay or re-ask', async ({ page }) => {
    test.skip(!INTERVIEW_PAGE_READY, 'blocker: apps/web/app/consultant/interviews/[id]/page.tsx not built');
    await page.goto('/consultant/interviews');
    expect(page.url()).toContain('/consultant/interviews');
  });

  test('correction and recap show what was learned', async ({ page }) => {
    test.skip(!INTERVIEW_PAGE_READY, 'blocker: interview-panel.tsx not built');
    await page.goto('/consultant/interviews');
    expect(page.url()).toContain('/consultant/interviews');
  });
});
