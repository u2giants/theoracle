// Increment 3 — Teams transcript subscription manager.
//
// Graph transcript subscriptions max out near 1 hour and must be renewed by a
// machine, not a human (this is the "always-on listener stays armed" piece — no
// one re-authenticates anything). We keep TWO standing subscriptions alive:
// ad-hoc ("Meet Now") calls AND scheduled online meetings — see
// ../lib/graph-transcripts.ts (TRANSCRIPT_RESOURCES / ensureAllSubscriptions).
//
// Two entry points, both calling the same idempotent ensureAllSubscriptions():
//   - teamsSubscriptionRenewCron: every 30 min, keeps both subscriptions alive.
//   - teamsSubscriptionManagerTask: triggered by the webhook on lifecycle events
//     (reauthorizationRequired / subscriptionRemoved / missed) for prompt repair.
//
// NOTE: this deliberately reuses the single existing 30-min schedule for both
// resources — Trigger.dev is at its 10/10 schedule limit (AGENTS.md §10), so do
// NOT add another schedules.task() here.
//
// Requires the AZURE_* + TEAMS_* env in the Trigger.dev project (see
// ../lib/graph-transcripts.ts). When unset, ensure* no-ops with action
// 'skipped_no_config' rather than throwing.

import { task, schedules } from '@trigger.dev/sdk/v3';
import { ensureAllSubscriptions, type EnsureResult } from '../lib/graph-transcripts';

async function runEnsure(context: string): Promise<EnsureResult[]> {
  const results = await ensureAllSubscriptions();
  console.log(`[teams-subscription-manager] (${context})`, JSON.stringify(results));
  return results;
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
