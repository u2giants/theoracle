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
};

async function graph(token: string, path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${GRAPH}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, 'content-type': 'application/json', ...(init?.headers ?? {}) },
    signal: AbortSignal.timeout(15_000),
  });
}

async function installedOracleApp(token: string, userId: string, botId: string): Promise<string | null> {
  const res = await graph(
    token,
    `/users/${encodeURIComponent(userId)}/teamwork/installedApps?$expand=teamsApp,teamsAppDefinition($expand=bot)`,
  );
  if (!res.ok) return null;
  const data = (await res.json()) as { value?: InstalledApp[] };
  const hit = (data.value ?? []).find((app) => app.teamsAppDefinition?.bot?.id === botId);
  return hit?.teamsApp?.id ?? null;
}

export async function installOracleForTenant(opts: { dryRun?: boolean } = {}): Promise<InstallResult> {
  const botId = process.env.MICROSOFT_BOT_APP_ID;
  if (!botId) throw new Error('MICROSOFT_BOT_APP_ID is not set');
  const token = await getGraphAccessToken();
  const users = (await listTenantUsers()).filter(
    (u) => u.accountEnabled && u.email.endsWith(TENANT_DOMAIN),
  );
  const result: InstallResult = {
    users: users.length,
    installed: 0,
    already: 0,
    failed: 0,
    failures: [],
    catalogId: process.env.TEAMS_APP_CATALOG_ID ?? null,
  };
  const has = new Set<string>();
  for (const user of users) {
    const found = await installedOracleApp(token, user.id, botId);
    if (found) {
      has.add(user.id);
      result.catalogId ??= found;
    }
  }
  result.already = has.size;
  if (!result.catalogId) throw new Error('Oracle Teams app is installed for nobody; cannot find its catalog id');
  if (opts.dryRun) return result;
  for (const user of users) {
    if (has.has(user.id)) continue;
    const res = await graph(token, `/users/${encodeURIComponent(user.id)}/teamwork/installedApps`, {
      method: 'POST',
      body: JSON.stringify({ 'teamsApp@odata.bind': `${GRAPH}/appCatalogs/teamsApps/${result.catalogId}` }),
    });
    if (res.ok) result.installed += 1;
    else if (res.status === 409) result.already += 1;
    else {
      result.failed += 1;
      result.failures.push(`${res.status} ${(await res.text().catch(() => '')).slice(0, 160)}`);
    }
  }
  return result;
}
