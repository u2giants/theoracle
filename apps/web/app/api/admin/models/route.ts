// GET /api/admin/models
//
// Server-side proxy for https://openrouter.ai/api/v1/models/user
// Keeps OPENROUTER_API_KEY out of the browser.
// Restricted to admins.

import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';

export const dynamic = 'force-dynamic';

type OpenRouterModel = {
  id: string;
  name: string;
  context_length: number | null;
  architecture?: {
    // e.g. "text+image->text", "text->text+image", "text+image+file->text"
    modality?: string;
  };
  pricing: {
    prompt: string;    // cost per token (string decimal)
    completion: string;
  } | null;
  // Array of generation params the model supports, e.g. ["tools", "reasoning", ...]
  supported_generation_params?: string[];
};

type OpenRouterResponse = {
  data: OpenRouterModel[];
};

/**
 * Derive boolean capability flags from the raw OpenRouter model object.
 *
 * modality format:  "<inputs>-><outputs>"
 *   inputs  can contain: "text", "image", "file"
 *   outputs can contain: "text", "image"
 *
 * supported_generation_params examples: ["tools", "reasoning", "temperature", ...]
 * NOTE: this field exists on the public /models endpoint but may be absent or
 * incomplete on /models/user — so we also apply a known-family pattern as
 * a reliable fallback for tool use.
 */

/**
 * Pattern matching model families that are documented to support function/tool
 * calling. Covers Anthropic, OpenAI, Google, Meta Llama 3.1+, Mistral Large
 * family, Mixtral, Qwen, Command-R, DeepSeek Chat, Grok, and Phi-3+.
 *
 * Intentionally excludes: pure reasoning models (o1-mini, r1), image-gen
 * models, and ancient (<2023) models that predate tool-call support.
 */
const TOOL_CAPABLE_PATTERN =
  /^(anthropic\/|openai\/gpt-4|openai\/gpt-3\.5-turbo|openai\/o[1-9](?!-mini)|google\/gemini|meta-llama\/llama-3|mistralai\/mistral-(?:large|medium|small|nemo)|mistralai\/mixtral|cohere\/command-r|qwen\/qwen|deepseek\/deepseek-chat|x-ai\/grok|microsoft\/phi-3|microsoft\/phi-4|nvidia\/)/i;

function parseCapabilities(m: OpenRouterModel) {
  const modality = m.architecture?.modality ?? '';
  const arrowIdx = modality.indexOf('->');
  const inputPart  = arrowIdx >= 0 ? modality.slice(0, arrowIdx) : modality;
  const outputPart = arrowIdx >= 0 ? modality.slice(arrowIdx + 2) : '';
  const params     = m.supported_generation_params ?? [];

  return {
    // Can process image input (vision)
    vision: inputPart.includes('image'),
    // Can process file/document input (PDF, docx, etc.)
    files: inputPart.includes('file'),
    // Supports tool / function calling.
    // Primary: API field (present on some endpoints).
    // Fallback: known model-family pattern.
    tools: params.includes('tools') || TOOL_CAPABLE_PATTERN.test(m.id),
    // Has extended reasoning / chain-of-thought (o1, o3, r1, Gemini thinking, etc.)
    reasoning:
      params.includes('reasoning') ||
      /thinking|\bo[13]\b|r1-0[0-9]|deepseek-r1/i.test(m.id),
    // Can generate images as output
    imageGen: outputPart.includes('image'),
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
      // Don't cache — always reflect the user's actual model access.
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

  // Debug: log the raw capability fields of the first few models so we can
  // verify what OpenRouter actually returns for supported_generation_params.
  // Remove once confirmed.
  const sample = (json.data ?? []).slice(0, 3);
  console.log(
    '[admin/models] raw capability sample:',
    JSON.stringify(
      sample.map((m) => ({
        id: m.id,
        modality: m.architecture?.modality,
        supported_generation_params: m.supported_generation_params,
      })),
      null,
      2,
    ),
  );

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
