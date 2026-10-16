import { task } from '@trigger.dev/sdk/v3';

/**
 * Bounded outbound adapter for S08 in-meeting participation.
 *
 * This task records an outbound intent and its provider idempotency key. It
 * never auto-sends. Only an explicit authorized send action may deliver, and a
 * replayed idempotency key returns the prior receipt instead of a second send.
 */

export type MeetingOutboundChannel = 'meeting_text' | 'meeting_chat';

export interface MeetingOutboundIntent {
  intentId: string;
  meetingId: string;
  turnId: string;
  channel: MeetingOutboundChannel;
  body: string;
  idempotencyKey: string;
  createdAt: string;
}

export interface MeetingDeliveryReceipt {
  receiptId: string;
  intentId: string;
  idempotencyKey: string;
  status: 'recorded' | 'sent' | 'failed';
  channel?: MeetingOutboundChannel;
  sentAt?: string;
  providerMessageId?: string;
}

const recorded = new Map<string, MeetingDeliveryReceipt>();
const bodies = new Map<string, string>();

function requireText(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim() || value !== value.trim()) {
    throw new Error(`${field} required`);
  }
  return value;
}

export function providerIdempotencyKey(meetingId: string, intentId: string, channel: MeetingOutboundChannel): string {
  return `${meetingId}|${intentId}|${channel}`;
}

export function buildIntent(payload: unknown): MeetingOutboundIntent {
  const p = payload as Record<string, unknown>;
  const intentId = requireText(p.intentId, 'intentId');
  const meetingId = requireText(p.meetingId, 'meetingId');
  const turnId = requireText(p.turnId, 'turnId');
  const body = requireText(p.body, 'body');
  const channel = p.channel as MeetingOutboundChannel;
  if (channel !== 'meeting_text' && channel !== 'meeting_chat') {
    throw new Error('unsupported outbound channel');
  }
  const createdAt = requireText(p.createdAt, 'createdAt');
  const idempotencyKey = providerIdempotencyKey(meetingId, intentId, channel);
  return { intentId, meetingId, turnId, channel, body, idempotencyKey, createdAt };
}

export function recordIntent(intent: MeetingOutboundIntent): MeetingDeliveryReceipt {
  const existing = recorded.get(intent.idempotencyKey);
  if (existing) {
    if (bodies.get(intent.idempotencyKey) !== intent.body) {
      throw new Error('conflicting outbound body under idempotency key');
    }
    return existing;
  }
  const receipt: MeetingDeliveryReceipt = {
    receiptId: `dr-${intent.intentId}`,
    intentId: intent.intentId,
    idempotencyKey: intent.idempotencyKey,
    status: 'recorded',
  };
  recorded.set(intent.idempotencyKey, receipt);
  bodies.set(intent.idempotencyKey, intent.body);
  return receipt;
}

export function markSent(
  idempotencyKey: string,
  fields: { receiptId: string; channel: MeetingOutboundChannel; sentAt: string; providerMessageId: string },
): MeetingDeliveryReceipt {
  const prior = recorded.get(idempotencyKey);
  if (!prior) throw new Error('unknown idempotency key');
  if (prior.status === 'sent') return prior;
  if (!fields.sentAt || !fields.providerMessageId) {
    throw new Error('sent receipt requires sentAt and providerMessageId');
  }
  const receipt: MeetingDeliveryReceipt = {
    receiptId: fields.receiptId,
    intentId: prior.intentId,
    idempotencyKey,
    status: 'sent',
    channel: fields.channel,
    sentAt: fields.sentAt,
    providerMessageId: fields.providerMessageId,
  };
  recorded.set(idempotencyKey, receipt);
  return receipt;
}

export function replay(idempotencyKey: string): MeetingDeliveryReceipt | undefined {
  return recorded.get(idempotencyKey);
}

/** Records intent only. Never calls a provider. */
export const oracle2MeetingOutboundRecord = task({
  id: 'oracle2-meeting-outbound-record',
  run: async (payload: unknown): Promise<MeetingDeliveryReceipt> => {
    return recordIntent(buildIntent(payload));
  },
});

/**
 * Delivery is a separate authorized act. This task refuses to run without an
 * explicit authorizedSend token and a provider receipt, and it is idempotent.
 */
export const oracle2MeetingOutboundDeliver = task({
  id: 'oracle2-meeting-outbound-deliver',
  run: async (payload: unknown): Promise<MeetingDeliveryReceipt> => {
    const p = payload as Record<string, unknown>;
    if (p.authorizedSend !== true) {
      throw new Error('outbound delivery requires explicit authorized send');
    }
    const idempotencyKey = requireText(p.idempotencyKey, 'idempotencyKey');
    const channel = p.channel as MeetingOutboundChannel;
    if (channel !== 'meeting_text' && channel !== 'meeting_chat') {
      throw new Error('unsupported outbound channel');
    }
    return markSent(idempotencyKey, {
      receiptId: requireText(p.receiptId, 'receiptId'),
      channel,
      sentAt: requireText(p.sentAt, 'sentAt'),
      providerMessageId: requireText(p.providerMessageId, 'providerMessageId'),
    });
  },
});
