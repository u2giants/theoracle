// Google Gemini model list source.
// Calls generativelanguage.googleapis.com/v1beta/models, which returns only
// Gemini models (not the full Vertex Model Garden). Authenticates using a
// short-lived Bearer token derived from the SA JSON in
// GOOGLE_APPLICATION_CREDENTIALS_JSON via a standard JWT assertion flow.
// Node's built-in `crypto` module handles the RS256 signing — no extra deps.

import { createSign } from 'crypto';
import type { RawProviderModel } from './types';

interface GeminiApiModel {
  name: string;                            // "models/gemini-2.5-flash"
  displayName?: string;
  supportedGenerationMethods?: string[];
  inputTokenLimit?: number;
  outputTokenLimit?: number;
}

interface GeminiModelsResponse {
  models?: GeminiApiModel[];
  nextPageToken?: string;
}

async function getAccessToken(saJson: string): Promise<string> {
  const sa = JSON.parse(saJson) as { client_email: string; private_key: string };
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

export async function fetchGoogleModels(): Promise<RawProviderModel[]> {
  const saJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
  if (!saJson) throw new Error('GOOGLE_APPLICATION_CREDENTIALS_JSON not set');

  const token = await getAccessToken(saJson);
  const results: RawProviderModel[] = [];
  let pageToken: string | undefined;

  do {
    const url = new URL('https://generativelanguage.googleapis.com/v1beta/models');
    url.searchParams.set('pageSize', '100');
    if (pageToken) url.searchParams.set('pageToken', pageToken);

    const res = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      signal: AbortSignal.timeout(10_000),
    });

    if (!res.ok) {
      throw new Error(`Gemini models list failed: ${res.status} ${await res.text()}`);
    }

    const body = (await res.json()) as GeminiModelsResponse;
    pageToken = body.nextPageToken;

    for (const m of body.models ?? []) {
      if (!m.supportedGenerationMethods?.includes('generateContent')) continue;
      const modelId = m.name.replace(/^models\//, '');
      results.push({
        id: `google/${modelId}`,
        provider: 'google',
        displayName: m.displayName ?? modelId,
        contextLength: m.inputTokenLimit ?? null,
        maxOutputTokens: m.outputTokenLimit ?? null,
        source: 'google_api',
      });
    }
  } while (pageToken);

  return results;
}
