import { schedules } from '@trigger.dev/sdk/v3';
import { getDirectDb } from '@oracle/db/client';
import { refreshModelCatalog } from '@oracle/ai';

/**
 * Keep the admin model catalog fresh without requiring a human to press the
 * refresh button. The UI reads the persisted model_capabilities table; this
 * task updates that table from the direct provider APIs plus OpenRouter
 * enrichment.
 */
export const modelCatalogRefreshTask = schedules.task({
  id: 'model-catalog-refresh-nightly',
  // 07:15 UTC is overnight for the US Eastern users of this app.
  cron: '15 7 * * *',
  run: async () => {
    const db = getDirectDb();
    const result = await refreshModelCatalog(db);

    if (result.errors.length > 0) {
      console.warn('[model-catalog-refresh-nightly] partial refresh', {
        errors: result.errors,
        unenrichedCount: result.unenrichedIds.length,
      });
    }

    return {
      ok: true,
      written: result.written,
      refreshedAt: result.refreshedAt,
      errors: result.errors,
      unenrichedCount: result.unenrichedIds.length,
    };
  },
});
