// §10 end-to-end adversarial proof: actual_native_pipeline_after_refresh.
//
// BLOCKER (named): no replacement-journey page or endpoint family exists under
// apps/web/app. The browser uploads a real binary while the backend seeds an old
// model/graph-evidence result; the native pipeline must be visible after refresh.
// This spec is intentionally skipped until that page/endpoint family lands.
// Invented/synthetic data only. Never company data, never a real provider.
import { test, expect } from '@playwright/test';

test.describe('replacement-journey', () => {
  test.skip('actual_native_pipeline_after_refresh', async ({ page }) => {
    // Intentionally empty. Skipped blocker:
    // replacement journey page/endpoint family is not implemented in apps/web/app,
    // so the browser cannot upload a real binary against a native pipeline route.
    // Required hostile case (plan §10): browser uploads real binary but backend
    // seeds old model/graph-evidence result; the refreshed page must show the
    // actual native pipeline output, never the seeded stale evidence.
    expect(page).toBeDefined();
  });
});
