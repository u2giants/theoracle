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

/** Raw getAllTranscripts item — the union of fields both callers read. */
interface RawTranscript {
  transcriptContentUrl?: string | null;
  meetingId?: string | null;
  callId?: string | null;
  createdDateTime?: string | null;
  endDateTime?: string | null;
  meetingOrganizer?: { user?: { id?: string | null } | null } | null;
}

/**
 * Page a per-organizer `getAllTranscripts` function by recursive TIME BISECTION
 * instead of by Graph's `@odata.nextLink`.
 *
 * Both the onlineMeetings (v1.0) and adhocCalls (beta) getAllTranscripts
 * functions have a server-side pagination defect: once a window holds more than
 * one page of transcripts, Graph either hands back a malformed nextLink or fails
 * the call outright with `startIndex ('-1')` (a 400) — even though we send no
 * paging params. High-volume organizers therefore 400 on the very first
 * full-range call. So we never page Graph's way: we query a time window, and if
 * it 400s (too big) OR returns a "more pages" link we can't follow, we split the
 * window in half and recurse into each half, down to a 1-minute floor. Every
 * transcript lands in exactly one small-enough window that returns cleanly;
 * results dedupe on transcript content URL across the shared boundary. Recovers
 * all transcripts whether or not Graph's own paging works.
 *
 * Resilience contract (per organizer): a 403 on the very FIRST call throws
 * (genuine access/policy gap the caller wants surfaced); 404 is an empty window;
 * a 400 bisects; network/timeout skips that window; a per-organizer call cap
 * backstops runaway subdivision.
 */
async function pageTranscriptsByTime(
  token: string,
  organizerId: string,
  sinceIso: string,
  buildUrl: (startIso: string, endIso: string) => string,
  label: string,
): Promise<RawTranscript[]> {
  const out: RawTranscript[] = [];
  const seen = new Set<string>();
  const MIN_WINDOW_MS = 60_000; // 1-minute floor; below this we stop subdividing
  const MAX_CALLS = 250; // backstop against runaway subdivision for one organizer
  // Work stack of [startIso, endIso] windows to fetch.
  const stack: Array<[string, string]> = [[sinceIso, new Date().toISOString()]];
  let calls = 0;
  let firstCall = true;

  while (stack.length > 0 && calls < MAX_CALLS) {
    const [start, end] = stack.pop()!;
    calls += 1;
    let res: Response;
    try {
      res = await fetch(buildUrl(start, end), {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(30_000),
      });
    } catch (err) {
      // Network error / timeout — skip this window, keep scanning the rest.
      console.warn(`[graph-transcripts] ${label} fetch error for ${organizerId} (${start}..${end})`, err);
      firstCall = false;
      continue;
    }

    if (!res.ok) {
      const body = (await res.text().catch(() => '')).slice(0, 200);
      if (firstCall && res.status === 403) {
        throw new Error(`${label} forbidden (403) for organizer ${organizerId}: ${body}`);
      }
      firstCall = false;
      if (res.status === 404) continue; // no transcripts in this window
      const startMs = Date.parse(start);
      const endMs = Date.parse(end);
      // A too-big window (Graph's startIndex/pagination bug) surfaces as 400 —
      // bisect and retry the halves until each is small enough to return cleanly.
      if (res.status === 400 && endMs - startMs > MIN_WINDOW_MS) {
        const midIso = new Date((startMs + endMs) / 2).toISOString();
        stack.push([start, midIso], [midIso, end]);
      } else {
        console.warn(
          `[graph-transcripts] ${label} ${res.status} for ${organizerId} (${start}..${end}): ${body}`,
        );
      }
      continue;
    }

    firstCall = false;
    const page = (await res.json()) as { value?: RawTranscript[]; '@odata.nextLink'?: string };
    const startMs = Date.parse(start);
    const endMs = Date.parse(end);
    // Still more than one page and we can't follow the broken nextLink — subdivide
    // to capture the rest rather than collect a partial window.
    if (page['@odata.nextLink'] && endMs - startMs > MIN_WINDOW_MS) {
      const midIso = new Date((startMs + endMs) / 2).toISOString();
      stack.push([start, midIso], [midIso, end]);
      continue;
    }
    for (const t of page.value ?? []) {
      const id = t.transcriptContentUrl ?? null;
      if (id) {
        if (seen.has(id)) continue;
        seen.add(id);
      }
      out.push(t);
    }
  }

  if (calls >= MAX_CALLS) {
    console.warn(
      `[graph-transcripts] ${label} hit ${MAX_CALLS}-call cap for ${organizerId}; results may be partial`,
    );
  }
  return out;
}

/**
 * Scheduled-meeting transcripts for one organizer created at/after `sinceIso`.
 * Mirrors the change-notification payload shape so each result can be handed to
 * teams-transcript-ingestion exactly like a live notification. Uses the STABLE
 * v1.0 function and time-bisection paging (see pageTranscriptsByTime).
 *
 * The PULL endpoint is per-user: users/{id}/onlineMeetings/getAllTranscripts —
 * distinct from the tenant-wide SUBSCRIPTION resource
 * communications/onlineMeetings/getAllTranscripts. See diagnose-transcripts.ps1.
 */
export async function getOnlineMeetingTranscripts(
  organizerId: string,
  sinceIso: string,
): Promise<BackfillTranscript[]> {
  const cfg = getConfigOrNull();
  if (!cfg) return [];
  const token = await getToken(cfg);
  const raws = await pageTranscriptsByTime(
    token,
    organizerId,
    sinceIso,
    (startIso, endIso) =>
      `${GRAPH_V1}/users/${organizerId}/onlineMeetings/getAllTranscripts(meetingOrganizerUserId='${organizerId}',startDateTime=${startIso},endDateTime=${endIso})`,
    'getAllTranscripts',
  );
  return raws.map((t) => ({
    transcriptContentUrl: t.transcriptContentUrl ?? null,
    resourcePath: null,
    meetingId: t.meetingId ?? null,
    callId: t.callId ?? null,
    createdDateTime: t.createdDateTime ?? null,
  }));
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
 * Same resilience contract as getOnlineMeetingTranscripts, and the same
 * time-bisection paging (see pageTranscriptsByTime) — the adhocCalls function
 * has the identical pagination defect, so we never follow its nextLink.
 */
export async function getAdhocCallTranscripts(
  organizerId: string,
  sinceIso: string,
): Promise<AdhocCallTranscript[]> {
  const cfg = getConfigOrNull();
  if (!cfg) return [];
  const token = await getToken(cfg);
  const raws = await pageTranscriptsByTime(
    token,
    organizerId,
    sinceIso,
    (startIso, endIso) =>
      `${GRAPH_BETA}/users/${organizerId}/adhocCalls/getAllTranscripts(userId='${organizerId}',startDateTime=${startIso},endDateTime=${endIso})`,
    'adhoc getAllTranscripts',
  );
  return raws.map((t) => ({
    transcriptContentUrl: t.transcriptContentUrl ?? null,
    meetingId: t.meetingId ?? null,
    callId: t.callId ?? null,
    organizerId: t.meetingOrganizer?.user?.id ?? organizerId,
    createdDateTime: t.createdDateTime ?? null,
    endDateTime: t.endDateTime ?? null,
  }));
}
