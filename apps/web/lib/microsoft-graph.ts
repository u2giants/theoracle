// Microsoft Graph client for backend tenant operations.
//
// This is the *app-only* path: we mint an access token via OAuth2
// client_credentials against the registered Entra app (TheOracle,
// appId ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc), then call Graph as the app.
// The app has the `User.Read.All` Application permission with admin
// consent granted in the tenant.
//
// This is intentionally separate from the SSO path: SSO is a delegated
// (per-user) flow that runs through Supabase Auth; this module runs in the
// admin backend for read-the-directory operations like "list users I haven't
// yet onboarded into Oracle."
//
// Token cache: in-memory per server instance. Tokens last 60 minutes; we
// refetch 5 minutes before expiry to avoid clock-skew misses.

const TOKEN_ENDPOINT = (tenantId: string) =>
  `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`;
const GRAPH_USERS_URL =
  'https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail,userPrincipalName,jobTitle,accountEnabled&$top=100';

export interface GraphConfig {
  tenantId: string;
  clientId: string;
  clientSecret: string;
}

export interface GraphTenantUser {
  id: string;
  displayName: string;
  /** Primary mail address. Falls back to userPrincipalName when null. */
  email: string;
  jobTitle: string | null;
  accountEnabled: boolean;
}

export class GraphNotConfiguredError extends Error {
  constructor() {
    super(
      'Microsoft Graph backend not configured. Set AZURE_TENANT_ID, ' +
        'AZURE_GRAPH_CLIENT_ID, and AZURE_GRAPH_CLIENT_SECRET in the ' +
        'environment to enable the M365 user pull.',
    );
    this.name = 'GraphNotConfiguredError';
  }
}

export function getGraphConfigOrNull(): GraphConfig | null {
  const tenantId = process.env.AZURE_TENANT_ID;
  const clientId = process.env.AZURE_GRAPH_CLIENT_ID;
  const clientSecret = process.env.AZURE_GRAPH_CLIENT_SECRET;
  if (!tenantId || !clientId || !clientSecret) return null;
  return { tenantId, clientId, clientSecret };
}

// ─── Token cache ────────────────────────────────────────────────────────────

interface CachedToken {
  accessToken: string;
  /** Absolute epoch ms at which we should refetch. */
  refreshAt: number;
}
let cachedToken: CachedToken | null = null;
const REFETCH_SKEW_MS = 5 * 60 * 1000;

async function getAccessToken(cfg: GraphConfig): Promise<string> {
  const now = Date.now();
  if (cachedToken && cachedToken.refreshAt > now) {
    return cachedToken.accessToken;
  }

  const body = new URLSearchParams({
    client_id: cfg.clientId,
    client_secret: cfg.clientSecret,
    scope: 'https://graph.microsoft.com/.default',
    grant_type: 'client_credentials',
  });

  const res = await fetch(TOKEN_ENDPOINT(cfg.tenantId), {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
    // Token mint is fast; bail at 10s if Entra is slow.
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Microsoft Graph token request failed (${res.status}): ${detail.slice(0, 500)}`,
    );
  }
  const data = (await res.json()) as {
    access_token: string;
    expires_in: number;
  };

  cachedToken = {
    accessToken: data.access_token,
    refreshAt: now + Math.max(60_000, data.expires_in * 1000 - REFETCH_SKEW_MS),
  };
  return cachedToken.accessToken;
}

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Page through Graph /users and return every active tenant user. For a 49-
 * user tenant this is one round trip; the loop handles tenants up to several
 * thousand users without changes.
 *
 * Throws GraphNotConfiguredError when the env vars aren't set so callers can
 * render a "configure me" notice instead of a 500.
 */
export async function listTenantUsers(): Promise<GraphTenantUser[]> {
  const cfg = getGraphConfigOrNull();
  if (!cfg) throw new GraphNotConfiguredError();
  const token = await getAccessToken(cfg);

  const all: GraphTenantUser[] = [];
  let nextUrl: string | undefined = GRAPH_USERS_URL;
  while (nextUrl) {
    const res = await fetch(nextUrl, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error(
        `Microsoft Graph /users failed (${res.status}): ${detail.slice(0, 500)}`,
      );
    }
    const page = (await res.json()) as {
      value: Array<{
        id: string;
        displayName: string | null;
        mail: string | null;
        userPrincipalName: string;
        jobTitle: string | null;
        accountEnabled: boolean | null;
      }>;
      '@odata.nextLink'?: string;
    };
    for (const u of page.value) {
      const email = u.mail ?? u.userPrincipalName;
      if (!email) continue;
      all.push({
        id: u.id,
        displayName: u.displayName ?? email,
        email: email.toLowerCase(),
        jobTitle: u.jobTitle,
        accountEnabled: u.accountEnabled ?? true,
      });
    }
    nextUrl = page['@odata.nextLink'];
  }
  return all;
}

// ─── Teams ad-hoc transcript subscriptions ──────────────────────────────────
//
// Ad-hoc "Meet Now" calls are NOT enumerable after the fact via
// getAllTranscripts(meetingOrganizerUserId=...) — that only covers *scheduled*
// meetings. The only way to capture ad-hoc-call transcripts is a standing
// change-notification subscription to `communications/adhocCalls/getAllTranscripts`.
//
// IMPORTANT operational facts (see DECISIONS / memory):
//   - "Listen going forward" only: a notification fires solely if the
//     subscription was active BEFORE transcription started. Past calls are gone.
//   - The resource is currently PREVIEW/beta and per-tenant flighted. If a
//     create call 4xxs on the v1.0 endpoint, retry against GRAPH_BETA_BASE.
//   - These notifications REQUIRE includeResourceData:true + an encryption
//     certificate (transcript content is sensitive; Graph encrypts the payload).
//   - Subscriptions are short-lived and MUST be renewed before expiry by the
//     teams-subscription-manager cron, or calls during the gap are lost forever.

const GRAPH_BASE = 'https://graph.microsoft.com/v1.0';
const GRAPH_BETA_BASE = 'https://graph.microsoft.com/beta';
export const ADHOC_TRANSCRIPTS_RESOURCE =
  'communications/adhocCalls/getAllTranscripts';

export interface CreateSubscriptionArgs {
  /** Public HTTPS endpoint that receives change notifications. */
  notificationUrl: string;
  /** Public HTTPS endpoint that receives lifecycle (reauth/expiry) pings. */
  lifecycleNotificationUrl: string;
  /** Base64 of the X.509 public certificate Graph uses to encrypt payloads. */
  encryptionCertificate: string;
  /** Our identifier for the cert above; echoed back on each notification. */
  encryptionCertificateId: string;
  /** Secret we set and verify on every inbound notification. */
  clientState: string;
  /** Minutes until expiry. Kept conservative; the cron renews well before. */
  expirationMinutes?: number;
  /** Force the beta endpoint (preview resource may require it in some tenants). */
  useBeta?: boolean;
}

export interface GraphSubscription {
  id: string;
  resource: string;
  expirationDateTime: string;
  notificationUrl: string;
}

function subscriptionsUrl(useBeta?: boolean): string {
  return `${useBeta ? GRAPH_BETA_BASE : GRAPH_BASE}/subscriptions`;
}

async function graphFetch(
  url: string,
  init: RequestInit,
  cfg: GraphConfig,
): Promise<Response> {
  const token = await getAccessToken(cfg);
  return fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(20_000),
  });
}

/**
 * Create the standing subscription for ad-hoc call transcripts. Returns the
 * subscription id + expiry so the manager can persist and renew it.
 */
export async function createAdhocTranscriptSubscription(
  args: CreateSubscriptionArgs,
): Promise<GraphSubscription> {
  const cfg = getGraphConfigOrNull();
  if (!cfg) throw new GraphNotConfiguredError();

  const expirationDateTime = new Date(
    Date.now() + (args.expirationMinutes ?? 55) * 60_000,
  ).toISOString();

  const res = await graphFetch(
    subscriptionsUrl(args.useBeta),
    {
      method: 'POST',
      body: JSON.stringify({
        changeType: 'created',
        resource: ADHOC_TRANSCRIPTS_RESOURCE,
        notificationUrl: args.notificationUrl,
        lifecycleNotificationUrl: args.lifecycleNotificationUrl,
        includeResourceData: true,
        encryptionCertificate: args.encryptionCertificate,
        encryptionCertificateId: args.encryptionCertificateId,
        clientState: args.clientState,
        expirationDateTime,
      }),
    },
    cfg,
  );

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Graph subscription create failed (${res.status}): ${detail.slice(0, 800)}`,
    );
  }
  const data = (await res.json()) as GraphSubscription;
  return data;
}

/** Extend an existing subscription's lifetime. Called by the renewal cron. */
export async function renewSubscription(
  subscriptionId: string,
  expirationMinutes = 55,
  useBeta?: boolean,
): Promise<GraphSubscription> {
  const cfg = getGraphConfigOrNull();
  if (!cfg) throw new GraphNotConfiguredError();
  const expirationDateTime = new Date(
    Date.now() + expirationMinutes * 60_000,
  ).toISOString();

  const res = await graphFetch(
    `${subscriptionsUrl(useBeta)}/${subscriptionId}`,
    { method: 'PATCH', body: JSON.stringify({ expirationDateTime }) },
    cfg,
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Graph subscription renew failed (${res.status}): ${detail.slice(0, 500)}`,
    );
  }
  return (await res.json()) as GraphSubscription;
}

/** List current subscriptions (used to reconcile / avoid duplicates). */
export async function listSubscriptions(
  useBeta?: boolean,
): Promise<GraphSubscription[]> {
  const cfg = getGraphConfigOrNull();
  if (!cfg) throw new GraphNotConfiguredError();
  const res = await graphFetch(subscriptionsUrl(useBeta), { method: 'GET' }, cfg);
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Graph subscription list failed (${res.status}): ${detail.slice(0, 500)}`,
    );
  }
  const data = (await res.json()) as { value: GraphSubscription[] };
  return data.value ?? [];
}

/** Delete a subscription (cleanup / rotation). */
export async function deleteSubscription(
  subscriptionId: string,
  useBeta?: boolean,
): Promise<void> {
  const cfg = getGraphConfigOrNull();
  if (!cfg) throw new GraphNotConfiguredError();
  const res = await graphFetch(
    `${subscriptionsUrl(useBeta)}/${subscriptionId}`,
    { method: 'DELETE' },
    cfg,
  );
  if (!res.ok && res.status !== 404) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Graph subscription delete failed (${res.status}): ${detail.slice(0, 500)}`,
    );
  }
}

/**
 * Fetch the raw transcript content (WebVTT) for a callTranscript resource.
 * `transcriptResourcePath` is the Graph path delivered in the notification,
 * e.g. "users/{id}/onlineMeetings/{id}/transcripts/{id}".
 */
export async function getTranscriptVtt(
  transcriptResourcePath: string,
): Promise<string> {
  const cfg = getGraphConfigOrNull();
  if (!cfg) throw new GraphNotConfiguredError();
  const token = await getAccessToken(cfg);
  const path = transcriptResourcePath.replace(/^\/+/, '');
  const res = await fetch(
    `${GRAPH_BASE}/${path}/content?$format=text/vtt`,
    {
      headers: { Authorization: `Bearer ${token}`, Accept: 'text/vtt' },
      signal: AbortSignal.timeout(30_000),
    },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Graph transcript content fetch failed (${res.status}): ${detail.slice(0, 500)}`,
    );
  }
  return res.text();
}

/** For tests / one-off scripts. Clears the in-memory token cache. */
export function _resetGraphTokenCache(): void {
  cachedToken = null;
}
