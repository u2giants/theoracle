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

/** All M365 user ids — the candidate meeting organizers for backfill. */
export async function listUserIds(): Promise<string[]> {
  const cfg = getConfigOrNull();
  if (!cfg) return [];
  const token = await getToken(cfg);
  const ids: string[] = [];
  let url: string | undefined =
    'https://graph.microsoft.com/v1.0/users?$select=id&$top=100';
  while (url) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) {
      throw new Error(`list users failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
    }
    const page = (await res.json()) as {
      value?: Array<{ id: string }>;
      '@odata.nextLink'?: string;
    };
    for (const u of page.value ?? []) if (u.id) ids.push(u.id);
    url = page['@odata.nextLink'];
  }
  return ids;
}

export interface BackfillTranscript {
  transcriptContentUrl: string | null;
  resourcePath: string | null;
  meetingId: string | null;
  callId: string | null;
  createdDateTime: string | null;
}

/**
 * Scheduled-meeting transcripts for one organizer created at/after `sinceIso`.
 * Mirrors the change-notification payload shape so each result can be handed to
 * teams-transcript-ingestion exactly like a live notification. Best-effort per
 * organizer: a 403/404 (no meetings, or policy gap for that user) yields [].
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
  while (url) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(20_000),
    });
    if (!res.ok) {
      // 404 = this organizer simply has no transcripts in the window (expected
      // for most users). Anything else (esp. 403 = app-access-policy gap) is a
      // real signal — surface it as an error rather than masking it as "empty".
      if (res.status === 404) return out;
      throw new Error(`getAllTranscripts failed (${res.status}) for organizer ${organizerId}: ${(await res.text()).slice(0, 300)}`);
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
  }
  return out;
}
