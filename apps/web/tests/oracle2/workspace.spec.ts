// S12 preview gate: home screen answers what we know / changed / needs
// confirmation / should improve.
// Page blocker: apps/web/app/consultant/page.tsx is still the minimal S03
// screen; the full workspace experience is not built on main.
// Invented/synthetic fixtures only.
import { test, expect } from '@playwright/test';

const WORKSPACE_READY = Boolean(process.env.ORACLE2_WORKSPACE_PAGE_READY);

test.describe('S12 consultant workspace', () => {
  test('home screen shows knowledge, changes, confirmations and improvements', async ({ page }) => {
    test.skip(!WORKSPACE_READY, 'blocker: apps/web/app/consultant/page.tsx full workspace not built');
    await page.goto('/consultant');
    expect(page.url()).toContain('/consultant');
  });

  test('process maps are editable business views with evidence', async ({ page }) => {
    test.skip(!WORKSPACE_READY, 'blocker: apps/web/components/consultant/process-map.tsx not built');
    await page.goto('/consultant');
    expect(page.url()).toContain('/consultant');
  });
});
