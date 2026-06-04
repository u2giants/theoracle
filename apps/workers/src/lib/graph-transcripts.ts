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
  subscriptionId?: string;
  expirationDateTime?: string;
  detail?: string;
};

// Subscriptions for this resource max out near 1h. Renew to ~50m and re-up
// whenever the remaining lifetime drops under 20m (the cron runs every 30m).
const RENEW_MINUTES = 50;
const RENEW_IF_WITHIN_MS = 20 * 60 * 1000;

/**
 * Ensure exactly one live ad-hoc transcript subscription exists pointing at our
 * webhook: renew it if it's near expiry, create it if it's missing. Safe to
 * call repeatedly (the renewal cron + webhook lifecycle events both call it).
 */
export async function ensureAdhocSubscription(): Promise<EnsureResult> {
  const cfg = getConfigOrNull();
  const subCfg = getSubscriptionConfigOrNull();
  if (!cfg || !subCfg) {
    return {
      action: 'skipped_no_config',
      detail: 'Azure creds or TEAMS_* subscription env not set in the worker environment',
    };
  }
  const token = await getToken(cfg);
  const authJson = { Authorization: `Bearer ${token}`, 'content-type': 'application/json' };

  const listRes = await fetch(`${GRAPH_BETA}/subscriptions`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(20_000),
  });
  if (!listRes.ok) {
    throw new Error(`list subscriptions failed (${listRes.status}): ${(await listRes.text()).slice(0, 300)}`);
  }
  const subs = ((await listRes.json()) as { value?: GraphSub[] }).value ?? [];
  const mine = subs.find(
    (s) => s.resource === ADHOC_RESOURCE && s.notificationUrl === subCfg.notificationUrl,
  );

  const nextExpiry = () => new Date(Date.now() + RENEW_MINUTES * 60_000).toISOString();

  if (mine) {
    if (Date.parse(mine.expirationDateTime) - Date.now() > RENEW_IF_WITHIN_MS) {
      return { action: 'ok', subscriptionId: mine.id, expirationDateTime: mine.expirationDateTime };
    }
    const res = await fetch(`${GRAPH_BETA}/subscriptions/${mine.id}`, {
      method: 'PATCH',
      headers: authJson,
      body: JSON.stringify({ expirationDateTime: nextExpiry() }),
      signal: AbortSignal.timeout(20_000),
    });
    if (!res.ok) {
      throw new Error(`renew failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
    }
    const r = (await res.json()) as GraphSub;
    return { action: 'renewed', subscriptionId: r.id, expirationDateTime: r.expirationDateTime };
  }

  const res = await fetch(`${GRAPH_BETA}/subscriptions`, {
    method: 'POST',
    headers: authJson,
    body: JSON.stringify({
      changeType: 'created',
      resource: ADHOC_RESOURCE,
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
    throw new Error(`create failed (${res.status}): ${(await res.text()).slice(0, 400)}`);
  }
  const r = (await res.json()) as GraphSub;
  return { action: 'created', subscriptionId: r.id, expirationDateTime: r.expirationDateTime };
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
