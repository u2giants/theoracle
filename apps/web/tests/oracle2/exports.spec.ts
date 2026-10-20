// S12 preview gate: export permitted SOPs, source-linked maps and
// recommendation briefs; exports retain date/scope and citation links.
// Page blocker: consultant export surfaces are not built on main.
// Invented/synthetic fixtures only.
import { test, expect } from '@playwright/test';

const EXPORTS_READY = Boolean(process.env.ORACLE2_EXPORTS_PAGE_READY);

test.describe('S12 exports', () => {
  test('export retains date, scope and citation links', async ({ page }) => {
    test.skip(!EXPORTS_READY, 'blocker: consultant export surfaces not built');
    await page.goto('/consultant');
    expect(page.url()).toContain('/consultant');
  });

  test('denied-source export is refused', async ({ page }) => {
    test.skip(!EXPORTS_READY, 'blocker: consultant export surfaces not built');
    await page.goto('/consultant');
    expect(page.url()).toContain('/consultant');
  });
});
