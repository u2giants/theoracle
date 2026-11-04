// Teams build-out phase 4: reach employees who never messaged the bot.
//
// The bot can only write to someone it has a conversation with. Installing
// the Oracle Teams app for a user (Graph `users/{id}/teamwork/installedApps`)
// makes Teams send the bot a conversationUpdate in that user's personal
// scope; the bot route stores the conversation reference from it. Needs the
// Graph application permission TeamsAppInstallation.ReadWriteForUser.All.
//
// The org catalog id of the Oracle app is read from an existing install whose
// bot id matches MICROSOFT_BOT_APP_ID (no extra AppCatalog permission), or
// from TEAMS_APP_CATALOG_ID when set.

import { getGraphAccessToken, listTenantUsers } from './microsoft-graph';

const GRAPH = 'https://graph.microsoft.com/v1.0';
const TENANT_DOMAIN = '@popcre.com';

type InstalledApp = {
  teamsApp?: { id?: string };
  teamsAppDefinition?: { bot?: { id?: string } | null };
};

export type InstallResult = {
  users: number;
  installed: number;
  already: number;
  failed: number;
  failures: string[];
  catalogId: string | null;
  nextCursor: string | null;
};

async function graph(token: string, path: string, init?: RequestInit): Promise<Response> {
  const url = new URL(path, `${GRAPH}/`);
  if (!url.href.startsWith(`${GRAPH}/`)) throw new Error('Invalid Graph pagination URL');
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(url, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, 'content-type': 'application/json', ...(init?.headers ?? {}) },
      signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000),
    });
    if (res.status !== 429 || attempt >= 1) return res;
    const retry = res.headers.get('retry-after');
    const delay = retry && /^\d+$/.test(retry) ? Number(retry) * 1000
      : retry ? Math.max(0, Date.parse(retry) - Date.now()) : 1000;
    // Long throttles are reported for retry by the caller, never retried early.
    if (!Number.isFinite(delay) || delay > 5000) return res;
    await new Promise((resolve) => setTimeout(resolve, delay));
    init?.signal?.throwIfAborted();
  }
}

async function installedOracleApp(token: string, userId: string, botId: string, signal: AbortSignal): Promise<string | null> {
  let path: string | undefined = `/v1.0/users/${encodeURIComponent(userId)}/teamwork/installedApps?$expand=teamsApp,teamsAppDefinition($expand=bot)`;
  const seen = new Set<string>();
  while (path) {
    if (seen.has(path) || seen.size >= 20) throw new Error('Graph pagination limit exceeded');
    seen.add(path);
    const res = await graph(token, path, { signal });
    if (!res.ok) throw new Error(`Graph installedApps read: ${res.status} ${(await res.text()).slice(0, 160)}`);
    const data = (await res.json()) as { value?: InstalledApp[]; '@odata.nextLink'?: string };
    const hit = (data.value ?? []).find((app) => app.teamsAppDefinition?.bot?.id === botId);
    if (hit?.teamsApp?.id) return hit.teamsApp.id;
    path = data['@odata.nextLink'];
  }
  return null;
}

export class TeamsInstallConfigurationError extends Error {}

async function concurrent<T>(items: T[], work: (item: T) => Promise<void>) {
  let index = 0;
  await Promise.all(Array.from({ length: Math.min(5, items.length) }, async () => {
    while (index < items.length) await work(items[index++]!);
  }));
}

// Each call processes at most ten users. Pass nextCursor into the next call;
// retry the same cursor after failures (existing installs are safely skipped).
export async function installOracleForTenant(opts: { dryRun?: boolean; cursor?: string } = {}): Promise<InstallResult> {
  const botId = process.env.MICROSOFT_BOT_APP_ID;
  if (!botId) throw new TeamsInstallConfigurationError('MICROSOFT_BOT_APP_ID is not set');
  const token = await getGraphAccessToken();
  const allUsers = (await listTenantUsers()).filter(
    (u) => u.accountEnabled && u.email.endsWith(TENANT_DOMAIN),
  );
  allUsers.sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const remaining = allUsers.filter((user) => !opts.cursor || user.id > opts.cursor);
  const users = remaining.slice(0, 10);
  const result: InstallResult = {
    users: allUsers.length,
    nextCursor: remaining.length > users.length ? users.at(-1)!.id : null,
    installed: 0,
    already: 0,
    failed: 0,
    failures: [],
    catalogId: process.env.TEAMS_APP_CATALOG_ID ?? null,
  };
  const signal = AbortSignal.timeout(200_000);
  const has = new Set<string>();
  await concurrent(users, async (user) => {
    let found: string | null;
    try {
      found = await installedOracleApp(token, user.id, botId, signal);
    } catch (err) {
      throw new Error(`${user.email} (${user.id}): ${err instanceof Error ? err.message : String(err)}`);
    }
    if (found) {
      has.add(user.id);
      result.catalogId ??= found;
    }
  });
  result.already = has.size;
  if (!users.length) return result;
  if (!result.catalogId) throw new TeamsInstallConfigurationError('Set TEAMS_APP_CATALOG_ID; no Oracle install was found in this batch');
  if (opts.dryRun !== false) return result;
  await concurrent(users, async (user) => {
    if (has.has(user.id)) return;
    try {
      const res = await graph(token, `/v1.0/users/${encodeURIComponent(user.id)}/teamwork/installedApps`, {
        signal,
        method: 'POST',
        body: JSON.stringify({ 'teamsApp@odata.bind': `${GRAPH}/appCatalogs/teamsApps/${result.catalogId}` }),
      });
      if (res.ok) result.installed += 1;
      else if (res.status === 409) result.already += 1;
      else {
        result.failed += 1;
        result.failures.push(`${user.email} (${user.id}): ${res.status} ${(await res.text().catch(() => '')).slice(0, 160)}`);
      }
    } catch (err) {
      result.failed += 1;
      result.failures.push(`${user.email} (${user.id}): ${err instanceof Error ? err.message : String(err)}`);
    }
  });
  return result;
}
