// Shared Bot Framework adapter for the Teams bot routes (messages and the
// step-12 proactive interview route).

import { CloudAdapter, ConfigurationBotFrameworkAuthentication } from 'botbuilder';

let adapterSingleton: CloudAdapter | null = null;

export function teamsBotAppId(): string {
  const appId = process.env.MICROSOFT_BOT_APP_ID;
  if (!appId) throw new Error('MICROSOFT_BOT_APP_ID is not configured');
  return appId;
}

export function getTeamsBotAdapter(): CloudAdapter {
  const appId = process.env.MICROSOFT_BOT_APP_ID;
  const appPassword = process.env.MICROSOFT_BOT_APP_PASSWORD;
  const appTenantId = process.env.MICROSOFT_BOT_TENANT_ID;
  if (!appId || !appPassword) {
    throw new Error('MICROSOFT_BOT_APP_ID / MICROSOFT_BOT_APP_PASSWORD are not configured');
  }
  if (!adapterSingleton) {
    adapterSingleton = new CloudAdapter(
      new ConfigurationBotFrameworkAuthentication({
        MicrosoftAppId: appId,
        MicrosoftAppPassword: appPassword,
        MicrosoftAppType: appTenantId ? 'SingleTenant' : 'MultiTenant',
        MicrosoftAppTenantId: appTenantId,
      }),
    );
  }
  return adapterSingleton;
}
