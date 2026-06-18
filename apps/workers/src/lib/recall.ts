const DEFAULT_RECALL_BASE_URL = 'https://us-east-1.recall.ai';

function recallBaseUrl(): string {
  return (process.env.RECALL_BASE_URL ?? DEFAULT_RECALL_BASE_URL).replace(/\/+$/, '');
}

function recallApiKey(): string {
  const key = process.env.RECALL_API_KEY;
  if (!key) throw new Error('RECALL_API_KEY is not configured');
  return key;
}

/**
 * Thrown when a Recall send fails for a reason that is likely transient
 * (network error, request timeout, or a 429/5xx response). Callers can catch
 * this specifically to log-and-continue instead of re-throwing into a Trigger
 * retry — important on the live-utterance path, where a retry would re-run the
 * task and hit the utterance dedup, silently dropping the interjection.
 */
export class RecallTransientSendError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'RecallTransientSendError';
  }
}

export async function sendRecallChatMessage(args: {
  botId: string;
  message: string;
}): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${recallBaseUrl()}/api/v1/bot/${args.botId}/send_chat_message/`, {
      method: 'POST',
      headers: {
        Authorization: recallApiKey(),
        accept: 'application/json',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        to: 'everyone',
        message: args.message.slice(0, 4096),
      }),
      signal: AbortSignal.timeout(15_000),
    });
  } catch (err) {
    // Network failure or timeout (AbortError) — treat as transient.
    throw new RecallTransientSendError(
      `Recall send_chat_message network failure: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 500);
    const message = `Recall send_chat_message failed (${res.status}): ${detail}`;
    // 429 (rate limited) and 5xx (server) are transient; 4xx (other) are not.
    if (res.status === 429 || res.status >= 500) {
      throw new RecallTransientSendError(message, res.status);
    }
    throw new Error(message);
  }
}
