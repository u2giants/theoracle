import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { logger, task } from '@trigger.dev/sdk/v3';
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
    // Failure recording: non-secret runtime facts only (no env values, no payload text).
    const bin = process.env.PYTHON_BIN_PATH || 'python';
    const script = './oracle2-python/oracle_brain/holistic_runtime.py';
    const probe = spawnSync(bin, ['-c', 'import sys; print(sys.version.split()[0])'], { encoding: 'utf8', timeout: 60_000 });
    logger.info('oracle2-python-preflight', {
      bin, binExists: existsSync(bin), scriptExists: existsSync(script), cwd: process.cwd(),
      probeStatus: probe.status, probeSignal: probe.signal, probeError: probe.error?.message ?? null,
      probeStdout: (probe.stdout ?? '').slice(0, 200), probeStderr: (probe.stderr ?? '').slice(-500),
    });
    const result = await python.runScript('./oracle2-python/oracle_brain/holistic_runtime.py',
      ['answer', JSON.stringify(identifiers)]);
    const status = JSON.parse(result.stdout);
    if (status.status !== 'completed') throw new Error('Holistic corpus answer failed');
    return status;
  },
});
