import crypto from 'node:crypto';
import { Buffer } from 'node:buffer';

export type RecallSttProvider = 'elevenlabs_streaming' | 'assembly_ai_v3_streaming';

export interface RecallCreateBotArgs {
  meetingUrl: string;
  webhookUrl: string;
  botName?: string;
  provider?: RecallSttProvider;
  metadata?: Record<string, string>;
}

function recallBaseUrl(): string {
  return (process.env.RECALL_BASE_URL ?? 'https://us-east-1.recall.ai').replace(/\/+$/, '');
}

function recallApiKey(): string {
  const key = process.env.RECALL_API_KEY;
  if (!key) throw new Error('RECALL_API_KEY is not configured');
  return key;
}

export function verifyRecallRequest(args: {
  secret: string;
  headers: Headers;
  payload: string | null;
}): void {
  const { secret, headers, payload } = args;
  const msgId = headers.get('webhook-id') ?? headers.get('svix-id');
  const msgTimestamp = headers.get('webhook-timestamp') ?? headers.get('svix-timestamp');
  const msgSignature = headers.get('webhook-signature') ?? headers.get('svix-signature');
  if (!secret || !secret.startsWith('whsec_')) {
    throw new Error('Recall verification secret is missing or invalid');
  }
  if (!msgId || !msgTimestamp || !msgSignature) {
    throw new Error('Missing Recall verification headers');
  }

  const key = Buffer.from(secret.slice('whsec_'.length), 'base64');
  const toSign = `${msgId}.${msgTimestamp}.${payload ?? ''}`;
  const expectedSig = crypto.createHmac('sha256', key).update(toSign).digest('base64');
  const expectedBytes = Buffer.from(expectedSig, 'base64');

  for (const versionedSig of msgSignature.split(' ')) {
    const [version, signature] = versionedSig.split(',');
    if (version !== 'v1' || !signature) continue;
    const actualBytes = Buffer.from(signature, 'base64');
    if (
      expectedBytes.length === actualBytes.length &&
      crypto.timingSafeEqual(new Uint8Array(expectedBytes), new Uint8Array(actualBytes))
    ) {
      return;
    }
  }
  throw new Error('No matching Recall signature found');
}

function providerConfig(provider: RecallSttProvider): Record<string, unknown> {
  if (provider === 'assembly_ai_v3_streaming') {
    return { assembly_ai_v3_streaming: {} };
  }
  return { elevenlabs_streaming: {} };
}

export async function createRecallLiveBot(args: RecallCreateBotArgs): Promise<unknown> {
  const res = await fetch(`${recallBaseUrl()}/api/v1/bot/`, {
    method: 'POST',
    headers: {
      Authorization: recallApiKey(),
      accept: 'application/json',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      meeting_url: args.meetingUrl,
      bot_name: args.botName ?? 'The Oracle',
      recording_config: {
        transcript: {
          provider: providerConfig(args.provider ?? 'elevenlabs_streaming'),
          diarization: { use_separate_streams_when_available: true },
        },
        realtime_endpoints: [
          {
            type: 'webhook',
            url: args.webhookUrl,
            events: ['transcript.data'],
          },
        ],
      },
      chat: {
        on_bot_join: {
          send_to: 'everyone',
          message:
            'The Oracle is listening for operational context and may ask a short clarification question if something sounds important.',
        },
      },
      metadata: {
        source: 'oracle_live_teams',
        stt_provider: args.provider ?? 'elevenlabs_streaming',
        ...(args.metadata ?? {}),
      },
    }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new Error(`Recall create bot failed (${res.status}): ${(await res.text()).slice(0, 500)}`);
  }
  return res.json();
}
