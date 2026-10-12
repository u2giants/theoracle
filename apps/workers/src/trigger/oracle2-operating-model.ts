import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';

export const oracle2OperatingModel = task({
  id: 'oracle2-operating-model-view',
  maxDuration: 120,
  retry: { maxAttempts: 1 },
  run: async (payload: { runId: string; workspaceId: string }) => {
    if (process.env.ORACLE2_CONFIRMED_GRAPH_URL || process.env.ORACLE2_PROJECTION_SIGNING_KEY
      || process.env.ORACLE2_CHECKPOINT_DATABASE_URL || process.env.SUPABASE_SERVICE_ROLE_KEY) {
      throw new Error('Operating-model worker has forbidden credentials');
    }
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuid.test(payload.runId) || !uuid.test(payload.workspaceId)) throw new Error('Invalid opaque view identity');
    const result = await python.runScript('./oracle2-python/oracle_brain/operating_model_cli.py',
      [JSON.stringify({ runId: payload.runId, workspaceId: payload.workspaceId })]);
    const status = JSON.parse(result.stdout);
    if (status.state !== 'completed') throw new Error('Operating model is not currently available');
    return status;
  },
});
