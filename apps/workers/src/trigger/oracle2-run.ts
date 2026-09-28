import { task, wait } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';
import { runRequest } from '@oracle/brain-contracts';

export const ORACLE2_EXTRACT_SCRIPT = './oracle2-python/oracle_brain/cli.py';

function assertExtractorIdentity() {
  if (process.env.ORACLE2_CONFIRMED_GRAPH_URL || process.env.ORACLE2_PROJECTION_SIGNING_KEY
      || process.env.ORACLE2_CHECKPOINT_DATABASE_URL || process.env.SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error('Extractor identity contains forbidden credentials');
  }
}

function syntheticRequest(payload: unknown) {
  const request = runRequest.parse(payload);
  if (request.mode !== 'synthetic') throw new Error('S02 transport is synthetic only');
  assertExtractorIdentity();
  return request;
}

export const oracle2Run = task({
  id: 'oracle2-synthetic-run',
  run: async (payload: unknown) => {
    const request = syntheticRequest(payload);
    const result = await python.runScript(ORACLE2_EXTRACT_SCRIPT, [JSON.stringify(request)]);
    return result.stdout;
  },
});

// Pause/resume proof: Python runs, the run checkpoints across a wait, and
// Python runs again in the resumed process.
export const oracle2PauseResume = task({
  id: 'oracle2-synthetic-pause-resume',
  run: async (payload: unknown) => {
    const request = syntheticRequest(payload);
    const before = await python.runScript(ORACLE2_EXTRACT_SCRIPT, [JSON.stringify(request)]);
    await wait.for({ seconds: 10 });
    assertExtractorIdentity();
    const after = await python.runScript(ORACLE2_EXTRACT_SCRIPT, [JSON.stringify(request)]);
    return { before: before.stdout, after: after.stdout };
  },
});
