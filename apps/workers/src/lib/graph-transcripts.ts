// Self-contained Microsoft Graph helper for the Teams transcript workers.
//
// This lives in apps/workers (a separate Trigger.dev process from apps/web), so
// it intentionally re-implements the small app-only token + subscription
// surface rather than importing apps/web/lib/microsoft-graph.ts (cross-app
// imports aren't allowed). If this and the web copy drift, the web one
// (apps/web/lib/microsoft-graph.ts) is the reference.
//
// Required env (set in the Trigger.dev project, NOT just Vercel):
//   AZURE_TENANT_ID, AZURE_GRAPH_CLIENT_ID, AZURE_GRAPH_CLIENT_SECRET
//   TEAMS_NOTIFICATION_URL          (https://oracle.designflow.app/api/teams/notifications)
//   TEAMS_NOTIFICATION_PUBLIC_CERT  (base64 DER of the public cert)
//   TEAMS_NOTIFICATION_CERT_ID      (matches the webhook's cert id)
//   TEAMS_WEBHOOK_CLIENT_STATE      (shared secret; same value as the webhook)

const GRAPH_BETA = 'https://graph.microsoft.com/beta';
const GRAPH_V1 = 'https://graph.microsoft.com/v1.0';
// Ad-hoc ("Meet Now") transcripts are only reachable via this subscription, and
// only on the beta endpoint (v1.0 rejects it).
const ADHOC_RESOURCE = 'communications/adhocCalls/getAllTranscripts';
// Scheduled-meeting transcripts come through a SEPARATE tenant-wide subscription.
// Ad-hoc and scheduled are distinct Graph resources, so each needs its own
// subscription (the "limit of 1" is per resource, so both can coexist).
const ONLINE_MEETINGS_RESOURCE = 'communications/onlineMeetings/getAllTranscripts';

// Every transcript resource we keep a standing subscription for.
export const TRANSCRIPT_RESOURCES = [ADHOC_RESOURCE, ONLINE_MEETINGS_RESOURCE] as const;

interface GraphConfig {
  tenantId: string;
  clientId: string;
  clientSecret: string;
}

function getConfigOrNull(): GraphConfig | null {
  const tenantId = process.env.AZURE_TENANT_ID;
  const clientId = process.env.AZURE_GRAPH_CLIENT_ID;
  const clientSecret = process.env.AZURE_GRAPH_CLIENT_SECRET;
  if (!tenantId || !clientId || !clientSecret) return null;
  return { tenantId, clientId, clientSecret };
}

let cachedToken: { token: string; refreshAt: number } | null = null;

async function getToken(cfg: GraphConfig): Promise<string> {
  if (cachedToken && cachedToken.refreshAt > Date.now()) return cachedToken.token;
  const body = new URLSearchParams({
    client_id: cfg.clientId,
    client_secret: cfg.clientSecret,
    scope: 'https://graph.microsoft.com/.default',
    grant_type: 'client_credentials',
  });
  const res = await fetch(
    `https://login.microsoftonline.com/${cfg.tenantId}/oauth2/v2.0/token`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body,
      signal: AbortSignal.timeout(10_000),
    },
  );
  if (!res.ok) {
    throw new Error(`Graph token failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
  }
  const data = (await res.json()) as { access_token: string; expires_in: number };
  cachedToken = {
    token: data.access_token,
    refreshAt: Date.now() + Math.max(60_000, data.expires_in * 1000 - 5 * 60 * 1000),
  };
  return cachedToken.token;
}

interface SubscriptionConfig {
  notificationUrl: string;
  encryptionCertificate: string;
  encryptionCertificateId: string;
  clientState: string;
}

function getSubscriptionConfigOrNull(): SubscriptionConfig | null {
  const notificationUrl = process.env.TEAMS_NOTIFICATION_URL;
  const encryptionCertificate = process.env.TEAMS_NOTIFICATION_PUBLIC_CERT;
  const encryptionCertificateId = process.env.TEAMS_NOTIFICATION_CERT_ID;
  const clientState = process.env.TEAMS_WEBHOOK_CLIENT_STATE;
  if (!notificationUrl || !encryptionCertificate || !encryptionCertificateId || !clientState) {
    return null;
  }
  return { notificationUrl, encryptionCertificate, encryptionCertificateId, clientState };
}

interface GraphSub {
  id: string;
  resource: string;
  expirationDateTime: string;
  notificationUrl: string;
}

export type EnsureResult = {
  action: 'created' | 'renewed' | 'ok' | 'skipped_no_config';
  resource?: string;
  subscriptionId?: string;
  expirationDateTime?: string;
  detail?: string;
};

// Subscriptions for this resource max out near 1h. Renew to ~50m and re-up
// whenever the remaining lifetime drops under 20m (the cron runs every 30m).
const RENEW_MINUTES = 50;
const RENEW_IF_WITHIN_MS = 20 * 60 * 1000;

const nextExpiry = () => new Date(Date.now() + RENEW_MINUTES * 60_000).toISOString();

/** List our subscriptions and find the one for `resource` on our webhook. */
async function findSub(
  token: string,
  resource: string,
  notificationUrl: string,
): Promise<GraphSub | undefined> {
  const listRes = await fetch(`${GRAPH_BETA}/subscriptions`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(20_000),
  });
  if (!listRes.ok) {
    throw new Error(`list subscriptions failed (${listRes.status}): ${(await listRes.text()).slice(0, 300)}`);
  }
  const subs = ((await listRes.json()) as { value?: GraphSub[] }).value ?? [];
  return subs.find((s) => s.resource === resource && s.notificationUrl === notificationUrl);
}

async function renewSub(token: string, sub: GraphSub): Promise<EnsureResult> {
  const res = await fetch(`${GRAPH_BETA}/subscriptions/${sub.id}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ expirationDateTime: nextExpiry() }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new Error(`renew failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
  }
  const r = (await res.json()) as GraphSub;
  return { action: 'renewed', resource: sub.resource, subscriptionId: r.id, expirationDateTime: r.expirationDateTime };
}

/**
 * Ensure exactly one live transcript subscription for `resource` points at our
 * webhook: renew it if near expiry, create it if missing. Safe to call
 * repeatedly (the renewal cron + webhook lifecycle events both call it).
 *
 * Resource-agnostic so the same logic serves both the ad-hoc and scheduled
 * online-meeting transcript subscriptions.
 */
export async function ensureSubscription(resource: string): Promise<EnsureResult> {
  const cfg = getConfigOrNull();
  const subCfg = getSubscriptionConfigOrNull();
  if (!cfg || !subCfg) {
    return {
      action: 'skipped_no_config',
      resource,
      detail: 'Azure creds or TEAMS_* subscription env not set in the worker environment',
    };
  }
  const token = await getToken(cfg);
  const authJson = { Authorization: `Bearer ${token}`, 'content-type': 'application/json' };

  const mine = await findSub(token, resource, subCfg.notificationUrl);
  if (mine) {
    if (Date.parse(mine.expirationDateTime) - Date.now() > RENEW_IF_WITHIN_MS) {
      return { action: 'ok', resource, subscriptionId: mine.id, expirationDateTime: mine.expirationDateTime };
    }
    return renewSub(token, mine);
  }

  const res = await fetch(`${GRAPH_BETA}/subscriptions`, {
    method: 'POST',
    headers: authJson,
    body: JSON.stringify({
      changeType: 'created',
      resource,
      notificationUrl: subCfg.notificationUrl,
      lifecycleNotificationUrl: subCfg.notificationUrl,
      includeResourceData: true,
      encryptionCertificate: subCfg.encryptionCertificate,
      encryptionCertificateId: subCfg.encryptionCertificateId,
      clientState: subCfg.clientState,
      expirationDateTime: nextExpiry(),
    }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    const errText = (await res.text()).slice(0, 400);
    // Benign race: the cron and a lifecycle event both tried to create at once,
    // or a previous create already succeeded ("limit of 1" per resource). Don't
    // fail — re-find the existing one and renew it.
    if (res.status === 403 && /reached its limit/i.test(errText)) {
      const existing = await findSub(token, resource, subCfg.notificationUrl);
      if (existing) return renewSub(token, existing);
    }
    throw new Error(`create failed (${res.status}): ${errText}`);
  }
  const r = (await res.json()) as GraphSub;
  return { action: 'created', resource, subscriptionId: r.id, expirationDateTime: r.expirationDateTime };
}

/** Back-compat wrapper: the ad-hoc ("Meet Now") transcript subscription. */
export function ensureAdhocSubscription(): Promise<EnsureResult> {
  return ensureSubscription(ADHOC_RESOURCE);
}

/** The scheduled online-meeting transcript subscription. */
export function ensureOnlineMeetingsSubscription(): Promise<EnsureResult> {
  return ensureSubscription(ONLINE_MEETINGS_RESOURCE);
}

/**
 * Ensure every standing transcript subscription (ad-hoc + scheduled). Each is
 * ensured independently so one failing (e.g. a tenant policy gap on scheduled
 * meetings) doesn't stop the other from being kept alive.
 */
export async function ensureAllSubscriptions(): Promise<EnsureResult[]> {
  return Promise.all(TRANSCRIPT_RESOURCES.map((r) => ensureSubscription(r)));
}

/**
 * Fetch a callTranscript's content as WebVTT. Prefers the decrypted
 * transcriptContentUrl from the notification; falls back to building the URL
 * from the resource path.
 */
export async function fetchTranscriptVtt(
  transcriptContentUrl: string | null,
  resourcePath: string | null,
): Promise<string> {
  const cfg = getConfigOrNull();
  if (!cfg) throw new Error('Graph not configured (AZURE_* env missing)');
  const token = await getToken(cfg);

  let url: string;
  if (transcriptContentUrl) {
    url = transcriptContentUrl.startsWith('http')
      ? transcriptContentUrl
      : `${GRAPH_V1}/${transcriptContentUrl.replace(/^\/+/, '')}`;
    if (!/[?&]\$format=/.test(url)) {
      url += (url.includes('?') ? '&' : '?') + '$format=text/vtt';
    }
  } else if (resourcePath) {
    url = `${GRAPH_V1}/${resourcePath.replace(/^\/+/, '')}/content?$format=text/vtt`;
  } else {
    throw new Error('No transcriptContentUrl or resourcePath provided');
  }

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'text/vtt' },
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) {
    throw new Error(`transcript content fetch failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
  }
  return res.text();
}

/**
 * Map of lowercased M365 display name -> primary email, for resolving Teams
 * transcript speakers (VTT carries display names only). Best-effort: returns an
 * empty map if Graph isn't configured or the call fails, so ingestion can fall
 * back to display-name matching. One page covers a tenant of a few hundred users.
 */
export async function listDisplayNameToEmail(): Promise<Map<string, string>> {
  const cfg = getConfigOrNull();
  if (!cfg) return new Map();
  const token = await getToken(cfg);
  const map = new Map<string, string>();
  let url: string | undefined =
    'https://graph.microsoft.com/v1.0/users?$select=displayName,mail,userPrincipalName&$top=100';
  while (url) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) break; // best-effort — caller falls back to name matching
    const page = (await res.json()) as {
      value?: Array<{ displayName: string | null; mail: string | null; userPrincipalName: string | null }>;
      '@odata.nextLink'?: string;
    };
    for (const u of page.value ?? []) {
      const email = (u.mail ?? u.userPrincipalName ?? '').toLowerCase();
      if (u.displayName && email) map.set(u.displayName.trim().toLowerCase(), email);
    }
    url = page['@odata.nextLink'];
  }
  return map;
}

// ─── Backfill: pull already-completed scheduled-meeting transcripts ──────────
//
// Subscriptions only "listen going forward", so to recover transcripts from
// meetings that already happened we enumerate organizers and ask Graph for
// their meeting transcripts in a time window. Idempotency is handled downstream
// by teams-transcript-ingestion (dedupes on transcriptId), so re-running is safe.

export type GraphDirectoryUser = {
  id: string;
  name: string | null;
  mail: string | null;
  userPrincipalName: string | null;
};

/** All M365 users (id + display name/email) — the candidate meeting organizers. */
export async function listUsers(): Promise<GraphDirectoryUser[]> {
  const cfg = getConfigOrNull();
  if (!cfg) return [];
  const token = await getToken(cfg);
  const users: GraphDirectoryUser[] = [];
  let url: string | undefined =
    'https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail,userPrincipalName&$top=100';
  while (url) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) {
      throw new Error(`list users failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
    }
    const page = (await res.json()) as {
      value?: Array<{
        id: string;
        displayName: string | null;
        mail: string | null;
        userPrincipalName: string | null;
      }>;
      '@odata.nextLink'?: string;
    };
    for (const u of page.value ?? []) {
      if (u.id) {
        users.push({
          id: u.id,
          name: u.displayName ?? null,
          mail: u.mail ?? null,
          userPrincipalName: u.userPrincipalName ?? null,
        });
      }
    }
    url = page['@odata.nextLink'];
  }
  return users;
}

export interface BackfillTranscript {
  transcriptContentUrl: string | null;
  resourcePath: string | null;
  meetingId: string | null;
  callId: string | null;
  createdDateTime: string | null;
}

export interface AdhocCallTranscript {
  transcriptContentUrl: string | null;
  /** Always null for ad-hoc calls (no scheduled onlineMeeting object). */
  meetingId: string | null;
  callId: string | null;
  organizerId: string | null;
  createdDateTime: string | null;
  /** Transcription end time — with createdDateTime this gives the duration. */
  endDateTime: string | null;
}

export type MeetingParticipant = {
  name: string;
  email?: string;
};

export interface OnlineMeetingMetadata {
  subject: string | null;
  participants: MeetingParticipant[];
  startDateTime: string | null;
  endDateTime: string | null;
  durationSeconds: number | null;
}

type GraphIdentity = {
  displayName?: string | null;
  id?: string | null;
  user?: {
    id?: string | null;
    displayName?: string | null;
    userPrincipalName?: string | null;
    mail?: string | null;
  } | null;
};

type GraphMeetingParticipant = {
  identity?: GraphIdentity | null;
  upn?: string | null;
  emailAddress?: string | null;
};

function participantFromGraph(p: GraphMeetingParticipant | null | undefined): MeetingParticipant | null {
  const user = p?.identity?.user;
  const name = (user?.displayName ?? p?.identity?.displayName ?? '').trim();
  const email = (user?.mail ?? user?.userPrincipalName ?? p?.emailAddress ?? p?.upn ?? '').trim();
  if (!name && !email) return null;
  return email ? { name: name || email, email } : { name };
}

function uniqueParticipants(participants: Array<MeetingParticipant | null>): MeetingParticipant[] {
  const seen = new Set<string>();
  const out: MeetingParticipant[] = [];
  for (const p of participants) {
    if (!p) continue;
    const key = (p.email ?? p.name).trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
}

function durationSeconds(startDateTime: string | null, endDateTime: string | null): number | null {
  const start = startDateTime ? Date.parse(startDateTime) : NaN;
  const end = endDateTime ? Date.parse(endDateTime) : NaN;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return Math.round((end - start) / 1000);
}

/**
 * Fetch subject, scheduled participants, and scheduled duration from the
 * onlineMeeting resource. This is metadata only; transcript content is not
 * pulled here.
 */
export async function getOnlineMeetingMetadata(
  organizerId: string,
  meetingId: string | null,
): Promise<OnlineMeetingMetadata | null> {
  if (!meetingId) return null;
  const cfg = getConfigOrNull();
  if (!cfg) return null;
  const token = await getToken(cfg);
  const url =
    `${GRAPH_V1}/users/${encodeURIComponent(organizerId)}/onlineMeetings/` +
    `${encodeURIComponent(meetingId)}?$select=subject,startDateTime,endDateTime,participants`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new Error(
      `onlineMeeting metadata fetch failed (${res.status}) for organizer ${organizerId}: ` +
        `${(await res.text()).slice(0, 300)}`,
    );
  }
  const meeting = (await res.json()) as {
    subject?: string | null;
    startDateTime?: string | null;
    endDateTime?: string | null;
    participants?: {
      organizer?: GraphMeetingParticipant | null;
      attendees?: GraphMeetingParticipant[] | null;
    } | null;
  };
  const startDateTime = meeting.startDateTime ?? null;
  const endDateTime = meeting.endDateTime ?? null;
  return {
    subject: meeting.subject ?? null,
    participants: uniqueParticipants([
      participantFromGraph(meeting.participants?.organizer),
      ...(meeting.participants?.attendees ?? []).map((p) => participantFromGraph(p)),
    ]),
    startDateTime,
    endDateTime,
    durationSeconds: durationSeconds(startDateTime, endDateTime),
  };
}

/**
 * Scheduled-meeting transcripts for one organizer created at/after `sinceIso`.
 * Mirrors the change-notification payload shape so each result can be handed to
 * teams-transcript-ingestion exactly like a live notification.
 *
 * Resilient per organizer: only a first-page **403** (genuine app-access-policy
 * gap) throws — everything else keeps whatever was collected and stops. This
 * tolerates (a) Graph's beta pagination quirk where an `@odata.nextLink` comes
 * back with `startIndex=-1` (a 400 on page 2+), and (b) slow organizers that hit
 * the request timeout — neither should make one user abort the whole scan or
 * discard the page(s) we already have.
 */
export async function getOnlineMeetingTranscripts(
  organizerId: string,
  sinceIso: string,
): Promise<BackfillTranscript[]> {
  const cfg = getConfigOrNull();
  if (!cfg) return [];
  const token = await getToken(cfg);
  const out: BackfillTranscript[] = [];
  // The PULL endpoint is per-user: users/{id}/onlineMeetings/getAllTranscripts.
  // (Distinct from the tenant-wide SUBSCRIPTION resource
  // communications/onlineMeetings/getAllTranscripts.) See diagnose-transcripts.ps1.
  const endIso = new Date().toISOString();
  let url: string | undefined =
    `${GRAPH_BETA}/users/${organizerId}/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='${organizerId}',startDateTime=${sinceIso},endDateTime=${endIso})`;
  let firstPage = true;
  while (url) {
    let res: Response;
    try {
      res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(30_000),
      });
    } catch (err) {
      // Network error / timeout — keep what we have, don't abort the scan.
      console.warn(`[graph-transcripts] getAllTranscripts fetch error for ${organizerId}`, err);
      return out;
    }
    if (!res.ok) {
      const body = (await res.text().catch(() => '')).slice(0, 200);
      // A first-page 403 is a genuine access/policy gap worth surfacing.
      if (firstPage && res.status === 403) {
        throw new Error(`getAllTranscripts forbidden (403) for organizer ${organizerId}: ${body}`);
      }
      // A FIRST-PAGE 404 is no longer swallowed silently as "no transcripts". It
      // usually does mean the organizer has none, but it is ALSO what a wrong
      // request shape returns (the documented communications/... vs
      // users/{id}/onlineMeetings/... endpoint regression silently 404s). A
      // silent 404-as-empty is exactly how that bug would hide, so log it. A 400
      // on a nextLink is Graph's startIndex=-1 pagination quirk (end of pages).
      if (res.status === 404 && firstPage) {
        console.warn(
          `[graph-transcripts] getAllTranscripts 404 (first page) for ${organizerId} — treating as ` +
            `"no transcripts", but if you expected some, verify the endpoint shape ` +
            `(must be users/{id}/onlineMeetings/getAllTranscripts): ${body}`,
        );
      } else if (res.status !== 404) {
        console.warn(`[graph-transcripts] getAllTranscripts ${res.status} for ${organizerId}: ${body}`);
      }
      return out;
    }
    const page = (await res.json()) as {
      value?: Array<{
        transcriptContentUrl?: string | null;
        meetingId?: string | null;
        callId?: string | null;
        createdDateTime?: string | null;
      }>;
      '@odata.nextLink'?: string;
    };
    for (const t of page.value ?? []) {
      out.push({
        transcriptContentUrl: t.transcriptContentUrl ?? null,
        resourcePath: null,
        meetingId: t.meetingId ?? null,
        callId: t.callId ?? null,
        createdDateTime: t.createdDateTime ?? null,
      });
    }
    url = page['@odata.nextLink'];
    firstPage = false;
  }
  return out;
}

/**
 * Ad-hoc ("Meet Now" / group-chat) call transcripts for one organizer, created
 * in [sinceIso, now]. Ad-hoc calls are enumerable ONLY through this BETA
 * function (`adhocCalls/getAllTranscripts`, whose organizer param is named
 * `userId`); the `onlineMeetings` function excludes them by design. Requires the
 * `CallTranscripts.Read.All` application permission — the same one the standing
 * ad-hoc change-notification subscription already uses, so if live capture works
 * this does too.
 *
 * Same resilience contract as getOnlineMeetingTranscripts: a first-page 403 is a
 * genuine access gap and throws; 404 / other 4xx / timeout keep whatever we
 * collected and stop. Pages by following `@odata.nextLink` verbatim and never
 * sends `$top` — a documented Graph quirk where `$top` drops the nextLink and
 * yields the `startIndex ('-1')` 400 on page 2+.
 */
export async function getAdhocCallTranscripts(
  organizerId: string,
  sinceIso: string,
): Promise<AdhocCallTranscript[]> {
  const cfg = getConfigOrNull();
  if (!cfg) return [];
  const token = await getToken(cfg);
  const out: AdhocCallTranscript[] = [];
  const endIso = new Date().toISOString();
  let url: string | undefined =
    `${GRAPH_BETA}/users/${organizerId}/adhocCalls/getAllTranscripts(userId='${organizerId}',startDateTime=${sinceIso},endDateTime=${endIso})`;
  let firstPage = true;
  while (url) {
    let res: Response;
    try {
      res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(30_000),
      });
    } catch (err) {
      console.warn(`[graph-transcripts] adhoc getAllTranscripts fetch error for ${organizerId}`, err);
      return out;
    }
    if (!res.ok) {
      const body = (await res.text().catch(() => '')).slice(0, 200);
      if (firstPage && res.status === 403) {
        throw new Error(
          `adhoc getAllTranscripts forbidden (403) for organizer ${organizerId}: ${body}`,
        );
      }
      if (res.status === 404 && firstPage) {
        // Usually means "this organizer has no ad-hoc call transcripts". Logged
        // (not silently swallowed) because a wrong request shape also 404s.
        console.warn(
          `[graph-transcripts] adhoc getAllTranscripts 404 (first page) for ${organizerId} — ` +
            `treating as "no ad-hoc transcripts": ${body}`,
        );
      } else if (res.status !== 404) {
        console.warn(`[graph-transcripts] adhoc getAllTranscripts ${res.status} for ${organizerId}: ${body}`);
      }
      return out;
    }
    const page = (await res.json()) as {
      value?: Array<{
        transcriptContentUrl?: string | null;
        meetingId?: string | null;
        callId?: string | null;
        createdDateTime?: string | null;
        endDateTime?: string | null;
        meetingOrganizer?: { user?: { id?: string | null } | null } | null;
      }>;
      '@odata.nextLink'?: string;
    };
    for (const t of page.value ?? []) {
      out.push({
        transcriptContentUrl: t.transcriptContentUrl ?? null,
        meetingId: t.meetingId ?? null,
        callId: t.callId ?? null,
        organizerId: t.meetingOrganizer?.user?.id ?? organizerId,
        createdDateTime: t.createdDateTime ?? null,
        endDateTime: t.endDateTime ?? null,
      });
    }
    url = page['@odata.nextLink'];
    firstPage = false;
  }
  return out;
}
