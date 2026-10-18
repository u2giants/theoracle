import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';

// Isolated fresh invented permission only. No source text, retry or old job.
export const oracle2NativeInvented = task({
  id: 'oracle2-native-invented-v1',
  maxDuration: 120,
  retry: { maxAttempts: 1 },
  run: async (payload: { jobId: string; workspaceId: string }, { ctx }) => {
    if(process.env.SUPABASE_SERVICE_ROLE_KEY||process.env.OPENAI_API_KEY||process.env.OPENROUTER_API_KEY
      ||process.env.ORACLE2_CONFIRMED_GRAPH_URL||process.env.ORACLE2_PROJECTION_SIGNING_KEY
      ||process.env.ORACLE2_CHECKPOINT_DATABASE_URL)throw new Error('Native executor has forbidden credentials');
    if (Object.keys(payload).sort().join('|') !== 'jobId|workspaceId'
      || payload.jobId !== '9c9c7424-8e16-4f71-be10-c935160e16c7'
      || payload.workspaceId !== '6426980e-6287-4f58-9e94-d1cb49b5cd5d') {
      throw new Error('New opaque invented test identity required');
    }
    const result = await python.runScript('./oracle2-python/oracle_brain/hosting/native_trigger_v1.py',
      [JSON.stringify(payload), ctx.run.id]);
    let value: Record<string, unknown>;
    try { value = JSON.parse(result.stdout); } catch { throw new Error('Native test metadata unavailable'); }
    if (value.state !== 'completed' || value.job_id !== payload.jobId
      || value.workspace_id !== payload.workspaceId || value.sdk_version !== '1.4.0') {
      throw new Error('New native test did not complete');
    }
    return value;
  },
});
