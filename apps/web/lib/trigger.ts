// Server-side Trigger.dev task dispatcher.
//
// Wraps tasks.trigger() so callers don't need to handle the case where:
//   - TRIGGER_SECRET_KEY is not set (Trigger.dev not yet configured)
//   - The Trigger.dev API is unreachable
//   - Tasks are not yet deployed
//
// Returns true on successful dispatch, false otherwise. The failure is logged
// but not thrown, so the underlying business write (upload, message insert) is
// not lost just because Trigger.dev is unavailable.
//
// IMPORTANT: callers MUST check the boolean. Only a FEW tasks have a cron sweep
// that recovers un-dispatched work (e.g. `document-ingestion-sweep`). For tasks
// with NO sweep — claim-translation, extraction-ab-eval, teams-transcript-
// ingestion / discovery-scan, brain-synthesis (weekly only) — a swallowed
// `false` means the work NEVER runs. Surface it to the user; don't assume a sweep.

export async function triggerTask(
  taskId: string,
  payload: Record<string, unknown>,
): Promise<boolean> {
  const secretKey = process.env.TRIGGER_SECRET_KEY;
  if (!secretKey) {
    console.warn(
      `[trigger] TRIGGER_SECRET_KEY not configured — skipping trigger for "${taskId}". ` +
        'Set it in Vercel env to enable real-time task dispatch. Cron sweeps will pick up the work.',
    );
    return false;
  }

  try {
    // Dynamic import so this module works in environments where @trigger.dev/sdk
    // is installed but not configured (avoids TRIGGER_SECRET_KEY read at import time).
    const { tasks } = await import('@trigger.dev/sdk/v3');
    await tasks.trigger(taskId, payload);
    console.log(`[trigger] dispatched task "${taskId}"`, payload);
    return true;
  } catch (err) {
    // Non-fatal: the cron sweep will catch it.
    console.warn(`[trigger] could not dispatch task "${taskId}":`, err);
    return false;
  }
}

/**
 * Schedule the lull check for 60 seconds after the most recent user message.
 *
 * Trigger.dev's trailing debounce keeps one delayed run per channel and moves
 * it forward when another message arrives. The message ID in the payload lets
 * the worker fail closed if a newer message races with the delayed run.
 */
export async function triggerLullCheck(
  channelId: string,
  messageId: string,
): Promise<boolean> {
  const secretKey = process.env.TRIGGER_SECRET_KEY;
  if (!secretKey) {
    console.warn(
      '[trigger] TRIGGER_SECRET_KEY not configured - lull check was not scheduled.',
    );
    return false;
  }

  try {
    const { tasks } = await import('@trigger.dev/sdk/v3');
    await tasks.trigger(
      'lull-interjection',
      { channelId, messageId },
      {
        debounce: {
          key: `lull-interjection:${channelId}`,
          delay: '60s',
          mode: 'trailing',
        },
      },
    );
    console.log('[trigger] scheduled lull check', { channelId, messageId });
    return true;
  } catch (err) {
    console.warn('[trigger] could not schedule lull check:', err);
    return false;
  }
}

export type TriggerDispatchResult =
  | { dispatched: true; runId: string }
  | { dispatched: false; error: string };

/** Dispatch a task when the caller must show and retain the exact Trigger run ID. */
export async function triggerTaskWithResult(
  taskId: string,
  payload: Record<string, unknown>,
): Promise<TriggerDispatchResult> {
  if (!process.env.TRIGGER_SECRET_KEY) {
    return { dispatched: false, error: 'Trigger.dev is not configured.' };
  }
  try {
    const { tasks } = await import('@trigger.dev/sdk/v3');
    const handle = await tasks.trigger(taskId, payload);
    return { dispatched: true, runId: handle.id };
  } catch (err) {
    console.warn(`[trigger] could not dispatch task "${taskId}":`, err);
    return {
      dispatched: false,
      error: err instanceof Error ? err.message : 'Trigger.dev dispatch failed.',
    };
  }
}
