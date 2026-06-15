// Embeddings.
//
// Spec uses vector(1536) — the OpenAI text-embedding-3-small dimension.
// OpenRouter doesn't host that exact model, so:
//
//   1. If OPENAI_API_KEY is set, call OpenAI directly for text-embedding-3-small.
//   2. Otherwise, return a deterministic-zero vector (length 1536) so the rest
//      of the system can be exercised without breaking the column type.
//
// See DECISIONS.md D3.embeddings — do NOT silently swap the vector dimension.

import { EMBEDDING_DIM } from '@oracle/shared';

const OPENAI_EMBEDDING_URL = 'https://api.openai.com/v1/embeddings';
const MODEL = 'text-embedding-3-small';
/** Max inputs per embeddings request before we split into multiple calls. */
const MAX_BATCH = 256;

type EmbeddingResponse = {
  data: Array<{ index: number; embedding: number[] }>;
};

/**
 * Embed a single string. Returns a vector of length EMBEDDING_DIM.
 * Falls back to a zero vector if OPENAI_API_KEY isn't set.
 */
export async function embedText(text: string): Promise<{
  vector: number[];
  model: string;
  fallback: boolean;
}> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return { vector: new Array(EMBEDDING_DIM).fill(0), model: 'zero-stub', fallback: true };
  }

  const res = await fetch(OPENAI_EMBEDDING_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ model: MODEL, input: text }),
  });

  if (!res.ok) {
    throw new Error(`OpenAI embeddings call failed: ${res.status} ${await res.text()}`);
  }
  const body = (await res.json()) as EmbeddingResponse;
  const vector = body.data[0]?.embedding;
  if (!vector || vector.length !== EMBEDDING_DIM) {
    throw new Error(
      `OpenAI returned unexpected embedding length: ${vector?.length}. ` +
        `Spec locks vector(${EMBEDDING_DIM}).`,
    );
  }
  return { vector, model: MODEL, fallback: false };
}

export async function embedMany(texts: string[]): Promise<{
  vectors: number[][];
  model: string;
  fallback: boolean;
}> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return {
      vectors: texts.map(() => new Array(EMBEDDING_DIM).fill(0)),
      model: 'zero-stub',
      fallback: true,
    };
  }
  const vectors: number[][] = [];
  // The embeddings endpoint caps inputs per request; split into safe chunks
  // and concatenate results in order.
  for (let start = 0; start < texts.length; start += MAX_BATCH) {
    const chunk = texts.slice(start, start + MAX_BATCH);
    const res = await fetch(OPENAI_EMBEDDING_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ model: MODEL, input: chunk }),
    });
    if (!res.ok) {
      throw new Error(`OpenAI embeddings call failed: ${res.status} ${await res.text()}`);
    }
    const body = (await res.json()) as EmbeddingResponse;
    // The API does not guarantee response order — sort by `index` ascending.
    const sorted = [...body.data].sort((a, b) => a.index - b.index);
    if (sorted.length !== chunk.length) {
      throw new Error(
        `OpenAI returned ${sorted.length} embeddings for ${chunk.length} inputs.`,
      );
    }
    for (const d of sorted) {
      if (!d.embedding || d.embedding.length !== EMBEDDING_DIM) {
        throw new Error(
          `OpenAI returned unexpected embedding length: ${d.embedding?.length}. ` +
            `Spec locks vector(${EMBEDDING_DIM}).`,
        );
      }
      vectors.push(d.embedding);
    }
  }
  return {
    vectors,
    model: MODEL,
    fallback: false,
  };
}
