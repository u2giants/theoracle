// Admin → Settings → Model Pool
//
// Shows all available models from the three direct Oracle providers
// (Anthropic, OpenAI, Vertex/Gemini) with a checkbox grid: one column per
// stage (Interview, Extraction, Synthesis). Each stage has its own pool
// stored in settings.model_pool_{stage} as a JSON string[] of
// "provider/modelId" strings. Empty pool = fall back to the 6 curated
// Oracle catalog routes.

import { inArray } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { MODEL_POOL_SETTING_KEYS } from '@oracle/ai';
import { ModelPoolEditor } from './_components/model-pool-editor';

export default async function ModelPoolPage() {
  const db = getDirectDb();
  const keys = [
    MODEL_POOL_SETTING_KEYS.interview,
    MODEL_POOL_SETTING_KEYS.extraction,
    MODEL_POOL_SETTING_KEYS.synthesis,
  ];
  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(inArray(settings.key, keys));

  const lookup = new Map(rows.map((r) => [r.key, r.value]));
  function poolFor(key: string): string[] {
    const v = lookup.get(key);
    return Array.isArray(v) ? (v as string[]) : [];
  }

  const initial = {
    interview: poolFor(MODEL_POOL_SETTING_KEYS.interview),
    extraction: poolFor(MODEL_POOL_SETTING_KEYS.extraction),
    synthesis: poolFor(MODEL_POOL_SETTING_KEYS.synthesis),
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Model Pool</h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Pick which models appear in each stage&apos;s dropdown on the main
          Settings page. Three independent pools — Interview, Extraction,
          Synthesis. Oracle calls Anthropic, OpenAI, Google Vertex, DeepSeek,
          and Alibaba Qwen directly (no third-party proxy).
        </p>
        <p className="text-sm text-muted-foreground">
          Leaving a stage&apos;s pool empty falls back to the 6 curated
          Oracle catalog routes for that stage. Changes take effect
          immediately in the pickers on the main{' '}
          <a
            href="/admin/settings"
            className="underline underline-offset-2 text-foreground hover:text-foreground/70"
          >
            Settings page
          </a>
          .
        </p>
      </header>

      <ModelPoolEditor initial={initial} />
    </div>
  );
}
