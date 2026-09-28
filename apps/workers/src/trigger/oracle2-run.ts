import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';
import { runRequest } from '@oracle/brain-contracts';

export const oracle2Run = task({
  id: 'oracle2-synthetic-run',
  run: async (payload: unknown) => {
    const request = runRequest.parse(payload);
    if (request.mode !== 'synthetic') throw new Error('S02 transport is synthetic only');
    if (process.env.ORACLE2_CONFIRMED_GRAPH_URL || process.env.ORACLE2_PROJECTION_SIGNING_KEY
        || process.env.SUPABASE_SERVICE_ROLE_KEY) {
      throw new Error('Extractor identity contains forbidden credentials');
    }
    const result = await python.runScript('./services/oracle-brain/oracle_brain/cli.py', [JSON.stringify(request)]);
    return result.stdout;
  },
});
