/**
 * GoogleGeminiAdapter — direct Gemini Developer API integration via `@google/genai`.
 *
 * This is intentionally separate from `VertexGeminiAdapter`. Some Gemini API
 * models can appear in the admin model catalog before the configured Vertex
 * project/region can serve them. Routes with provider `google` call the
 * Gemini API with an API key; routes with provider `vertex` keep using ADC,
 * Vertex regions, explicit caches, and Vertex Batch Prediction.
 */

import { GoogleGenAI, ThinkingLevel } from '@google/genai';
import type { Content, GenerateContentResponse, Part } from '@google/genai';
import { createSign } from 'node:crypto';
import type { OracleObjectResult, OracleTextResult, OracleUsage } from '../client/types';
import type { ReasoningEffort } from '../routes';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import {
  flattenPlan,
  parseJsonOrRaw,
  tryZodParse,
  zodToJsonSchema,
} from './vertex-gemini-adapter';

export interface GoogleGeminiAdapterOptions {
  /** Gemini API key. Defaults to GEMINI_API_KEY, then GOOGLE_API_KEY. */
  apiKey?: string;
}

export class GoogleGeminiAdapter implements OracleProviderAdapter {
  readonly provider = 'google' as const;
  private readonly client: GoogleGenAI | null;
  private readonly serviceAccountJson: string | null;

  constructor(opts: GoogleGeminiAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.GEMINI_API_KEY ?? process.env.GOOGLE_API_KEY;
    this.serviceAccountJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON ?? null;
    if (!apiKey && !this.serviceAccountJson) {
      throw new Error(
        'GoogleGeminiAdapter: GEMINI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS_JSON is not set. Set one for google/* routes.',
      );
    }
    this.client = apiKey ? new GoogleGenAI({ apiKey }) : null;
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const callStartedAt = Date.now();

    const contents = buildContents(userMessage, providerOptions);
    const generationConfig = {
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined,
      maxOutputTokens:
        typeof providerOptions?.maxOutputTokens === 'number'
          ? providerOptions.maxOutputTokens
          : undefined,
      ...geminiThinkingConfig(route.reasoningEffort),
    };
    const response = this.client
      ? await this.client.models.generateContent({
          model: route.modelId,
          contents,
          config: {
            systemInstruction: systemPrompt || undefined,
            ...generationConfig,
          },
        })
      : await this.generateContentWithOAuth({
          modelId: route.modelId,
          contents,
          systemPrompt,
          generationConfig,
        });

    return {
      text: extractTextFromGeminiResponse(response),
      usage: normalizeGeminiUsage(response, Date.now() - callStartedAt),
      rawResponse: response,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const callStartedAt = Date.now();

    const contents: Content[] = [{ role: 'user', parts: [{ text: userMessage }] }];
    const jsonSchema = zodToJsonSchema(schema);
    const commonConfig = {
      temperature: 0.1,
      ...geminiThinkingConfig(route.reasoningEffort),
    };
    const sdkConfig = {
      ...commonConfig,
      responseMimeType: 'application/json',
      responseJsonSchema: jsonSchema as unknown,
    };
    const restConfig = {
      ...commonConfig,
      responseMimeType: 'application/json',
      responseSchema: toGeminiRestSchema(jsonSchema),
    };
    const response = this.client
      ? await this.client.models.generateContent({
          model: route.modelId,
          contents,
          config: sdkConfig,
        })
      : await this.generateContentWithOAuth({
          modelId: route.modelId,
          contents,
          systemPrompt,
          generationConfig: restConfig,
        });

    const text = extractTextFromGeminiResponse(response);
    const parsed = parseJsonOrRaw(text);
    const validated = tryZodParse<TOutput>(schema, parsed);

    return {
      object: (validated ?? parsed) as TOutput,
      usage: normalizeGeminiUsage(response, Date.now() - callStartedAt),
      rawResponse: response,
    };
  }

  private async generateContentWithOAuth(input: {
    modelId: string;
    contents: Content[];
    systemPrompt: string;
    generationConfig: Record<string, unknown>;
  }): Promise<GenerateContentResponse> {
    if (!this.serviceAccountJson) {
      throw new Error('GoogleGeminiAdapter: service account JSON missing for OAuth request.');
    }
    const token = await getGenerativeLanguageAccessToken(this.serviceAccountJson);
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${input.modelId}:generateContent`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          contents: input.contents,
          systemInstruction: input.systemPrompt
            ? { parts: [{ text: input.systemPrompt }] }
            : undefined,
          generationConfig: stripUndefined(input.generationConfig),
        }),
        signal: AbortSignal.timeout(60_000),
      },
    );
    if (!res.ok) {
      throw new Error(`Gemini API generateContent failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as GenerateContentResponse;
  }
}

function buildContents(
  userMessage: string,
  providerOptions?: Record<string, unknown>,
): Content[] {
  const messages = providerOptions?.messages as
    | Array<{ role: 'user' | 'assistant' | 'system'; content: unknown }>
    | undefined;
  if (Array.isArray(messages) && messages.length > 0) {
    return messages
      .filter((m) => m.role !== 'system')
      .map((m) => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: toGeminiParts(m.content),
      }));
  }
  return [{ role: 'user', parts: [{ text: userMessage }] }];
}

function toGeminiParts(content: unknown): Part[] {
  if (typeof content === 'string') return [{ text: content }];
  if (!Array.isArray(content)) return [{ text: String(content ?? '') }];
  const parts: Part[] = [];
  for (const raw of content) {
    if (raw && typeof raw === 'object') {
      const part = raw as Record<string, unknown>;
      if (
        part.type === 'image' &&
        typeof part.data === 'string' &&
        typeof part.mimeType === 'string'
      ) {
        parts.push({ inlineData: { mimeType: part.mimeType, data: part.data } });
        continue;
      }
      if ((part.type === 'text' || part.type === undefined) && typeof part.text === 'string') {
        parts.push({ text: part.text });
        continue;
      }
    }
    parts.push({ text: String(raw) });
  }
  return parts;
}

function geminiThinkingConfig(effort: ReasoningEffort | undefined):
  | { thinkingConfig: { thinkingLevel: ThinkingLevel } }
  | Record<string, never> {
  if (!effort) return {};
  const thinkingLevel =
    effort === 'off' ? ThinkingLevel.MINIMAL
      : effort === 'low' ? ThinkingLevel.LOW
      : effort === 'medium' ? ThinkingLevel.MEDIUM
      : ThinkingLevel.HIGH;
  return { thinkingConfig: { thinkingLevel } };
}

function normalizeGeminiUsage(
  response: GenerateContentResponse,
  latencyMs: number,
): OracleUsage {
  const u = response.usageMetadata ?? {};
  return {
    inputTokens: u.promptTokenCount,
    outputTokens: u.candidatesTokenCount,
    cachedInputTokens: u.cachedContentTokenCount,
    reasoningTokens: u.thoughtsTokenCount,
    latencyMs,
    providerRequestId: response.responseId,
    rawUsageJson: u,
  };
}

function extractTextFromGeminiResponse(response: GenerateContentResponse): string {
  if (typeof response.text === 'string') return response.text;
  const candidateText = response.candidates
    ?.flatMap((candidate) => candidate.content?.parts ?? [])
    .map((part) => ('text' in part && typeof part.text === 'string' ? part.text : ''))
    .join('');
  return candidateText ?? '';
}

async function getGenerativeLanguageAccessToken(saJson: string): Promise<string> {
  const sa = parseServiceAccountJson(saJson);
  const now = Math.floor(Date.now() / 1000);

  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(
    JSON.stringify({
      iss: sa.client_email,
      scope: 'https://www.googleapis.com/auth/generative-language',
      aud: 'https://oauth2.googleapis.com/token',
      iat: now,
      exp: now + 3600,
    }),
  ).toString('base64url');

  const signer = createSign('SHA256');
  signer.update(`${header}.${payload}`);
  const sig = signer.sign({ key: sa.private_key, format: 'pem' }, 'base64url');
  const jwt = `${header}.${payload}.${sig}`;

  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt,
    }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(`Google token exchange failed: ${res.status} ${await res.text()}`);
  }
  const data = (await res.json()) as { access_token: string };
  return data.access_token;
}

function parseServiceAccountJson(saJson: string): { client_email: string; private_key: string } {
  try {
    return JSON.parse(saJson) as { client_email: string; private_key: string };
  } catch {
    // Vercel env pulls can materialize the PEM as literal newlines inside the
    // JSON string. Normalize just that field, then parse normally.
    const normalized = saJson.replace(
      /"private_key"\s*:\s*"([\s\S]*?)"/,
      (_match, key: string) => `"private_key":"${key.replace(/\r?\n/g, '\\n')}"`,
    );
    return JSON.parse(normalized) as { client_email: string; private_key: string };
  }
}

function stripUndefined<T extends Record<string, unknown>>(obj: T): Record<string, unknown> {
  return Object.fromEntries(Object.entries(obj).filter(([, value]) => value !== undefined));
}

function toGeminiRestSchema(schema: unknown): unknown {
  if (Array.isArray(schema)) return schema.map(toGeminiRestSchema);
  if (!schema || typeof schema !== 'object') return schema;

  const output: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(schema)) {
    if (key === '$schema' || key === 'additionalProperties') continue;
    output[key] = toGeminiRestSchema(value);
  }
  return output;
}
