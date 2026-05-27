// Admin → Settings → Model Pool
//
// Shows the 6 curated Oracle production routes (interview/extraction/synthesis
// × primary/fallback) as checkboxes. Checked route IDs form the "pool" that
// the model picker on the main settings page draws from.
//
// The pool is stored in settings.model_pool as a JSON string[] of routeIds.
// An empty pool means "use all 6 curated Oracle catalog routes".

import { eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { ModelPoolEditor } from './_components/model-pool-editor';

export default async function ModelPoolPage() {
  const db = getDirectDb();
  const poolRow = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'model_pool'))
    .limit(1);

  const currentPool: string[] = Array.isArray(poolRow[0]?.value)
    ? (poolRow[0]!.value as string[])
    : [];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Model Pool</h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Select which Oracle routes appear in the main Settings model pickers.
          All 6 production routes (interview, extraction, synthesis — primary +
          fallback each) are shown. Oracle routes inference directly through
          Anthropic, OpenAI, and Google Vertex — no third-party proxy.
        </p>
        <p className="text-sm text-muted-foreground">
          Leaving the pool empty falls back to the curated Oracle catalog (6
          pre-validated routes). Changes take effect immediately in the pickers
          on the main{' '}
          <a
            href="/admin/settings"
            className="underline underline-offset-2 text-foreground hover:text-foreground/70"
          >
            Settings page
          </a>
          .
        </p>
      </header>

      <ModelPoolEditor currentPool={currentPool} />
    </div>
  );
}
