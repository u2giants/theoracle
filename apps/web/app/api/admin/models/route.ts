// GET /api/admin/models
//
// Server-side proxy for https://openrouter.ai/api/v1/models/user
// Keeps OPENROUTER_API_KEY out of the browser.
// Restricted to admins.
//
// OpenRouter capability fields (verified against actual API schema):
//   architecture.input_modalities  — string[] e.g. ["text", "image", "file", "audio"]
//   architecture.output_modalities — string[] e.g. ["text"] or ["text", "image"]
//   supported_parameters           — string[] e.g. ["tools", "tool_choice", "temperature", ...]

import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';

export const dynamic = 'force-dynamic';

type OpenRouterModel = {
  id: string;
  name: string;
  context_length: number | null;
  architecture?: {
    input_modalities?: string[];   // what the model can accept as input
    output_modalities?: string[];  // what the model can produce as output
    tokenizer?: string | null;
    instruct_type?: string | null;
  };
  pricing: {
    prompt: string;       // cost per token (string decimal)
    completion: string;
  } | null;
  // Parameters the model natively supports.
  // Relevant values: "tools", "tool_choice", "structured_outputs", "response_format", "reasoning"
  supported_parameters?: string[];
};

type OpenRouterResponse = {
  data: OpenRouterModel[];
};

/**
 * Derive boolean capability flags from the raw OpenRouter model object.
 *
 * input_modalities:  ["text", "image", "file", "audio"]
 * output_modalities: ["text"] | ["text", "image"] | ["image"]
 * supported_parameters: ["tools", "tool_choice", "structured_outputs", ...]
 */
function parseCapabilities(m: OpenRouterModel) {
  const inputs  = m.architecture?.input_modalities  ?? [];
  const outputs = m.architecture?.output_modalities ?? [];
  const params  = m.supported_parameters            ?? [];

  return {
    // Can process image input (vision / multimodal)
    vision: inputs.includes('image'),
    // Can process file/document input (PDF, DOCX, etc.)
    files: inputs.includes('file'),
    // Supports tool / function calling (OpenAI-style)
    tools: params.includes('tools') || params.includes('tool_choice'),
    // Has extended reasoning / chain-of-thought
    // API field covers official reasoning models; regex catches named variants
    reasoning:
      params.includes('reasoning') ||
      /thinking|\bo[13]\b|r1-0[0-9]|deepseek-r1/i.test(m.id),
    // Can generate images as output (text-to-image models)
    imageGen: outputs.includes('image'),
  };
}

export async function GET() {
  // Admin-only.
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: 'OPENROUTER_API_KEY not configured' },
      { status: 500 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch('https://openrouter.ai/api/v1/models/user', {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      // Don't cache — always reflect current model availability.
      cache: 'no-store',
    });
  } catch (err) {
    console.error('[admin/models] fetch failed', err);
    return NextResponse.json(
      { error: 'Failed to reach OpenRouter' },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    const body = await upstream.text();
    console.error('[admin/models] OpenRouter error', upstream.status, body);
    return NextResponse.json(
      { error: 'OpenRouter returned an error', detail: body },
      { status: 502 },
    );
  }

  const json = (await upstream.json()) as OpenRouterResponse;

  // Return a trimmed, stable shape.
  // Prices are numeric (per 1M tokens) for clean client-side formatting.
  const models = (json.data ?? [])
    .map((m) => ({
      id: m.id,
      name: m.name ?? m.id,
      contextLength: m.context_length ?? null,
      // Per-1M-token prices as numbers (null = not disclosed).
      promptPer1M:
        m.pricing?.prompt != null
          ? parseFloat(m.pricing.prompt) * 1_000_000
          : null,
      completionPer1M:
        m.pricing?.completion != null
          ? parseFloat(m.pricing.completion) * 1_000_000
          : null,
      ...parseCapabilities(m),
    }))
    .sort((a, b) => a.id.localeCompare(b.id));

  return NextResponse.json({ models });
}
