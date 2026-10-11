import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';

// Dedicated reported-source preview; no source-bearing task payload.

// Only opaque identifiers cross Trigger; private question/source data is read in Python.
export const oracle2HolisticAnswer = task({
  id: 'oracle2-holistic-answer',
  maxDuration: 600,
  retry: { maxAttempts: 1 },
  run: async (payload: { runId: string; workspaceId: string; corpusDigest: string }) => {
    if (process.env.ORACLE2_ENVIRONMENT !== 'preview' || process.env.ORACLE2_CONFIRMED_GRAPH_URL
        || process.env.ORACLE2_PROJECTION_SIGNING_KEY || process.env.ORACLE2_CHECKPOINT_DATABASE_URL
        || process.env.SUPABASE_SERVICE_ROLE_KEY) {
      throw new Error('Holistic worker contains forbidden credentials or environment');
    }
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuid.test(payload.runId) || !uuid.test(payload.workspaceId)
        || !/^[a-f0-9]{64}$/.test(payload.corpusDigest)) {
      throw new Error('Invalid holistic run identifiers');
    }
    const identifiers = { runId: payload.runId, workspaceId: payload.workspaceId,
                          corpusDigest: payload.corpusDigest };
    const result = await python.runScript('./oracle2-python/oracle_brain/holistic_runtime.py',
      ['answer', JSON.stringify(identifiers)]);
    const status = JSON.parse(result.stdout);
    if (status.status !== 'completed') throw new Error('Holistic corpus answer failed');
    return status;
  },
});
