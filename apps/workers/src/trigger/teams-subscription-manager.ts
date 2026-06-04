// Increment 3 — Teams ad-hoc transcript subscription manager.
//
// Graph subscriptions for communications/adhocCalls/getAllTranscripts max out
// near 1 hour and must be renewed by a machine, not a human (this is the
// "always-on listener stays armed" piece — no one re-authenticates anything).
//
// Two entry points, both calling the same idempotent ensureAdhocSubscription():
//   - teamsSubscriptionRenewCron: every 30 min, keeps the subscription alive.
//   - teamsSubscriptionManagerTask: triggered by the webhook on lifecycle events
//     (reauthorizationRequired / subscriptionRemoved / missed) for prompt repair.
//
// Requires the AZURE_* + TEAMS_* env in the Trigger.dev project (see
// ../lib/graph-transcripts.ts). When unset, ensureAdhocSubscription() no-ops
// with action 'skipped_no_config' rather than throwing.

import { task, schedules } from '@trigger.dev/sdk/v3';
import { ensureAdhocSubscription, type EnsureResult } from '../lib/graph-transcripts';

async function runEnsure(context: string): Promise<EnsureResult> {
  const result = await ensureAdhocSubscription();
  console.log(`[teams-subscription-manager] (${context})`, JSON.stringify(result));
  return result;
}

// Webhook-triggered repair. Payload carries the lifecycle reason for logging.
export const teamsSubscriptionManagerTask = task({
  id: 'teams-subscription-manager',
  maxDuration: 60,
  run: async (payload: { reason?: string; subscriptionId?: string | null }) =>
    runEnsure(`lifecycle:${payload?.reason ?? 'manual'}`),
});

// Periodic keep-alive.
export const teamsSubscriptionRenewCron = schedules.task({
  id: 'teams-subscription-renew',
  cron: '*/30 * * * *',
  maxDuration: 60,
  run: async () => runEnsure('cron'),
});
