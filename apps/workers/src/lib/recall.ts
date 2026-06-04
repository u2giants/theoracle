const DEFAULT_RECALL_BASE_URL = 'https://us-west-2.recall.ai';

function recallBaseUrl(): string {
  return (process.env.RECALL_BASE_URL ?? DEFAULT_RECALL_BASE_URL).replace(/\/+$/, '');
}

function recallApiKey(): string {
  const key = process.env.RECALL_API_KEY;
  if (!key) throw new Error('RECALL_API_KEY is not configured');
  return key;
}

export async function sendRecallChatMessage(args: {
  botId: string;
  message: string;
}): Promise<void> {
  const res = await fetch(`${recallBaseUrl()}/api/v1/bot/${args.botId}/send_chat_message/`, {
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
  if (!res.ok) {
    throw new Error(`Recall send_chat_message failed (${res.status}): ${(await res.text()).slice(0, 500)}`);
  }
}
