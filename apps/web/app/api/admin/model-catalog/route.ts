// GET /api/admin/model-catalog
//
// Returns the full discovered model catalog for the admin model-pool page.
// All capabilities come from either provider /models APIs (Anthropic) or a
// Gemini Flash-Lite classification of the provider's official docs
// (OpenAI, Vertex). No hand-typed capability tables.
//
// Pass ?refresh=1 to bypass the in-memory cache and re-run discovery.
//
// Requires admin.
// Response: { models: ModelCatalogEntry[], providerErrors: string[], cached: boolean }

import { NextResponse, type NextRequest } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';
import {
  AnthropicAdapter,
  OpenAIAdapter,
  OracleAIClient,
  VertexGeminiAdapter,
  discoverModelCatalog,
  type ModelCapability,
} from '@oracle/ai';

export const dynamic = 'force-dynamic';

export type ModelCatalogEntry = {
  id: string;
  name: string;
  provider: 'anthropic' | 'openai' | 'google';
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  tools: boolean;
};

// Lazy OracleAIClient — adapter constructors throw if their env vars are
// missing, so we defer until request time. Same pattern as /api/chat.
let _client: OracleAIClient | null = null;
function getOracleClient(): OracleAIClient {
  if (!_client) {
    _client = new OracleAIClient({
      adapters: {
        anthropic: new AnthropicAdapter(),
        vertex: new VertexGeminiAdapter(),
        openai: new OpenAIAdapter(),
      },
      fallbackOnError: false,
    });
  }
  return _client;
}

function capabilityToEntry(cap: ModelCapability): ModelCatalogEntry {
  return {
    id: cap.id,
    name: cap.displayName,
    provider: cap.provider,
    contextLength: cap.contextLength,
    // Provider /models APIs don't expose pricing yet; left null. A follow-up
    // can layer a pricing source (e.g. the cost monitoring observability rows)
    // on top of the capability catalog.
    promptPer1M: null,
    completionPer1M: null,
    vision: cap.vision,
    tools: cap.toolCalling,
  };
}

export async function GET(req: NextRequest) {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const refresh = req.nextUrl.searchParams.get('refresh') === '1';

  try {
    const { catalog, providerErrors, cached } = await discoverModelCatalog(
      getOracleClient(),
      { force: refresh },
    );
    return NextResponse.json({
      models: catalog.map(capabilityToEntry),
      providerErrors,
      cached,
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'discovery_failed', detail: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
