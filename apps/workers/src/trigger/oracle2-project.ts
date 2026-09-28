import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';

export const oracle2Project = task({
  id: 'oracle2-synthetic-project',
  run: async () => {
    if (process.env.ORACLE2_CANDIDATE_GRAPH_URL || process.env.SUPABASE_SERVICE_ROLE_KEY) {
      throw new Error('Projector identity contains forbidden credentials');
    }
    if (!process.env.ORACLE2_CONFIRMED_GRAPH_URL || !process.env.ORACLE2_PROJECTION_SIGNING_KEY) {
      throw new Error('Projector identity incomplete');
    }
    const result = await python.runScript('./services/oracle-brain/oracle_brain/projector_cli.py');
    return result.stdout;
  },
});
