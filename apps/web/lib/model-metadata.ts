// Static metadata table for direct-provider models — pricing, context, caps.
// Shared between /api/admin/model-catalog (the picker source list) and
// /api/admin/models (the per-stage dropdown feed). Keyed by "provider/modelId"
// (the same id format used in settings.model_pool_*).

export type Provider = 'anthropic' | 'openai' | 'google';

export type ModelMeta = {
  contextLength: number;
  promptPer1M: number;
  completionPer1M: number;
  vision: boolean;
  reasoning?: boolean;
};

// `reasoning: true` = model supports a first-class reasoning / extended-thinking
// mode (hidden test-time compute, thinking budget, or thinking tokens), not
// just "is smart at multi-step problems." Per provider classifications:
//   - Anthropic Claude 3.7 Sonnet was the first hybrid-reasoning model;
//     the 4-series (Opus 4.7, Sonnet 4.6, Haiku 4.5) continues this.
//   - Google Gemini 2.5 family (Pro/Flash/Flash-Lite) and 2.0 Flash all ship
//     a thinking mode via `thinkingConfig`.
//   - OpenAI o-series (o1, o3, o4) are native reasoning models.
//   - GPT-4o, GPT-4 Turbo, Claude 3.5 Sonnet / 3.5 Haiku / 3 Opus, and
//     Gemini 1.5 are smart but pre-date the explicit reasoning-mode controls.
export const MODEL_META: Record<string, ModelMeta> = {
  // ── Anthropic ──────────────────────────────────────────────────────────────
  'anthropic/claude-opus-4-7':            { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 75,  vision: true,  reasoning: true  },
  'anthropic/claude-opus-4-7-20250514':   { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 75,  vision: true,  reasoning: true  },
  'anthropic/claude-sonnet-4-6':          { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true,  reasoning: true  },
  'anthropic/claude-sonnet-4-6-20250514': { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true,  reasoning: true  },
  'anthropic/claude-haiku-4-5':           { contextLength: 200_000, promptPer1M: 0.8,   completionPer1M: 4,   vision: true,  reasoning: true  },
  'anthropic/claude-haiku-4-5-20251001':  { contextLength: 200_000, promptPer1M: 0.8,   completionPer1M: 4,   vision: true,  reasoning: true  },
  'anthropic/claude-3-7-sonnet-20250219': { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true,  reasoning: true  },
  'anthropic/claude-3-5-sonnet-20241022': { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true  },
  'anthropic/claude-3-5-haiku-20241022':  { contextLength: 200_000, promptPer1M: 0.8,   completionPer1M: 4,   vision: true  },
  'anthropic/claude-3-opus-20240229':     { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 75,  vision: true  },

  // ── OpenAI ────────────────────────────────────────────────────────────────
  'openai/gpt-4o':                        { contextLength: 128_000, promptPer1M: 2.5,   completionPer1M: 10,  vision: true  },
  'openai/gpt-4o-2024-11-20':             { contextLength: 128_000, promptPer1M: 2.5,   completionPer1M: 10,  vision: true  },
  'openai/gpt-4o-mini':                   { contextLength: 128_000, promptPer1M: 0.15,  completionPer1M: 0.6, vision: true  },
  'openai/gpt-4o-mini-2024-07-18':        { contextLength: 128_000, promptPer1M: 0.15,  completionPer1M: 0.6, vision: true  },
  'openai/gpt-4-turbo':                   { contextLength: 128_000, promptPer1M: 10,    completionPer1M: 30,  vision: true  },
  'openai/o4-mini':                       { contextLength: 200_000, promptPer1M: 1.1,   completionPer1M: 4.4, vision: true,  reasoning: true },
  'openai/o3':                            { contextLength: 200_000, promptPer1M: 10,    completionPer1M: 40,  vision: true,  reasoning: true },
  'openai/o3-mini':                       { contextLength: 200_000, promptPer1M: 1.1,   completionPer1M: 4.4, vision: false, reasoning: true },
  'openai/o1':                            { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 60,  vision: true,  reasoning: true },
  'openai/o1-mini':                       { contextLength: 128_000, promptPer1M: 1.1,   completionPer1M: 4.4, vision: false, reasoning: true },

  // ── Google / Vertex AI ────────────────────────────────────────────────────
  'google/gemini-2.5-pro':                { contextLength: 1_000_000, promptPer1M: 1.25, completionPer1M: 10,  vision: true,  reasoning: true },
  'google/gemini-2.5-flash':              { contextLength: 1_000_000, promptPer1M: 0.15, completionPer1M: 0.6, vision: true,  reasoning: true },
  'google/gemini-2.5-flash-lite':         { contextLength: 1_000_000, promptPer1M: 0.1,  completionPer1M: 0.4, vision: true,  reasoning: true },
  'google/gemini-2.0-flash':              { contextLength: 1_000_000, promptPer1M: 0.1,  completionPer1M: 0.4, vision: true,  reasoning: true },
  'google/gemini-1.5-pro-002':            { contextLength: 2_000_000, promptPer1M: 1.25, completionPer1M: 5,   vision: true },
  'google/gemini-1.5-flash-002':          { contextLength: 1_000_000, promptPer1M: 0.075,completionPer1M: 0.3, vision: true },
};

export function providerOf(id: string): Provider {
  const prefix = id.split('/')[0];
  if (prefix === 'anthropic' || prefix === 'openai' || prefix === 'google') return prefix;
  return 'openai';
}
