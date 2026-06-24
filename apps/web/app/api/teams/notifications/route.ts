// POST/GET /api/teams/notifications
//
// The "always-on listener" for Microsoft Graph change notifications about
// Teams transcripts. Two standing subscriptions point here — ad-hoc calls
// (communications/adhocCalls/getAllTranscripts) and scheduled meetings
// (communications/onlineMeetings/getAllTranscripts). This handler is
// resource-agnostic: it decrypts whichever transcript fired and hands off to
// `teams-transcript-ingestion`, so no per-resource branching is needed.
//
// This endpoint MUST be deployed and publicly reachable BEFORE the subscription
// can be created — Graph validates it synchronously at subscription-create time
// by calling it with a ?validationToken=... that we have to echo back within
// 10 seconds. See apps/web/lib/microsoft-graph.ts createAdhocTranscriptSubscription.
//
// Responsibilities (kept deliberately fast — Graph disables subscriptions whose
// endpoint is slow or erroring):
//   1. Answer the validation handshake (echo validationToken as text/plain).
//   2. Verify the shared `clientState` secret on every real notification.
//   3. Decrypt the rich-notification payload to learn which transcript fired.
//   4. Hand off to the `teams-transcript-ingestion` worker — never fetch the
//      transcript or run extraction inline here.
//   5. Handle lifecycle events by asking the subscription manager to reauthorize.
//
// Both notificationUrl and lifecycleNotificationUrl on the subscription point
// here; we branch on the payload shape.

import { NextResponse, type NextRequest } from 'next/server';
import { triggerTask } from '@/lib/trigger';
import {
  decryptResourceData,
  type GraphEncryptedContent,
} from '@/lib/graph-notification-crypto';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs'; // node:crypto + Buffer needed for decryption

interface GraphNotification {
  subscriptionId?: string;
  clientState?: string;
  changeType?: string;
  resource?: string;
  resourceData?: { id?: string; '@odata.id'?: string } | null;
  encryptedContent?: GraphEncryptedContent;
  lifecycleEvent?: 'reauthorizationRequired' | 'subscriptionRemoved' | 'missed';
}

interface GraphNotificationEnvelope {
  value?: GraphNotification[];
}

/** Decrypted callTranscript shape — only the fields we use. */
interface DecryptedTranscript {
  transcriptContentUrl?: string;
  meetingId?: string;
  callId?: string;
  meetingOrganizer?: unknown;
  createdDateTime?: string;
}

/**
 * If this request is Graph's validation handshake, return the text/plain echo
 * response. Otherwise return null and let the caller process notifications.
 */
function handleValidation(req: NextRequest): NextResponse | null {
  const token = req.nextUrl.searchParams.get('validationToken');
  if (token === null) return null;
  return new NextResponse(token, {
    status: 200,
    headers: { 'content-type': 'text/plain' },
  });
}

export function GET(req: NextRequest): NextResponse {
  return handleValidation(req) ?? NextResponse.json({ ok: true });
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  // 1. Validation handshake (fires on subscription create + renewal).
  const validation = handleValidation(req);
  if (validation) return validation;

  // 2. Parse the envelope.
  let body: GraphNotificationEnvelope;
  try {
    body = (await req.json()) as GraphNotificationEnvelope;
  } catch {
    return NextResponse.json({ error: 'Bad JSON' }, { status: 400 });
  }
  const notifications = body.value ?? [];

  const expectedClientState = process.env.TEAMS_WEBHOOK_CLIENT_STATE;
  const privateKeyPem = process.env.TEAMS_NOTIFICATION_PRIVATE_KEY;

  for (const n of notifications) {
    // Lifecycle events (reauthorizationRequired / subscriptionRemoved / missed):
    // the subscription needs attention — let the manager handle it.
    if (n.lifecycleEvent) {
      void triggerTask('teams-subscription-manager', {
        reason: n.lifecycleEvent,
        subscriptionId: n.subscriptionId ?? null,
      });
      continue;
    }

    // Reject anything that doesn't carry our shared secret.
    if (expectedClientState && n.clientState !== expectedClientState) {
      console.warn('[teams/notifications] clientState mismatch — ignoring');
      continue;
    }

    // Decrypt to learn which transcript to fetch. We keep the unencrypted
    // `resource` path as a fallback so the worker can still locate it even if
    // decryption is unavailable (e.g. private key not yet configured).
    let transcriptContentUrl: string | null = null;
    let meetingId: string | null = null;
    let callId: string | null = null;
    if (n.encryptedContent && privateKeyPem) {
      try {
        const resource = decryptResourceData(
          n.encryptedContent,
          privateKeyPem,
        ) as DecryptedTranscript;
        transcriptContentUrl = resource.transcriptContentUrl ?? null;
        meetingId = resource.meetingId ?? null;
        callId = resource.callId ?? null;
      } catch (err) {
        console.error('[teams/notifications] decrypt failed', err);
      }
    }

    // Hand off. Fire-and-forget; the worker does the slow fetch + ingestion.
    void triggerTask('teams-transcript-ingestion', {
      resourcePath: n.resource ?? null,
      transcriptContentUrl,
      meetingId,
      callId,
      subscriptionId: n.subscriptionId ?? null,
    });
  }

  // Always acknowledge quickly so Graph doesn't retry or disable the sub.
  return new NextResponse(null, { status: 202 });
}
