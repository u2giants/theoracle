import { task } from '@trigger.dev/sdk/v3';
import { getDirectDb } from '@oracle/db/client';
import { sweepStaleMacroRelationships } from '@oracle/engines';

export const macroRelationshipStalenessSweepTask = task({
  id: 'macro-relationship-staleness-sweep',
  maxDuration: 120,
  run: async () => {
    const db = getDirectDb();
    const staleCount = await sweepStaleMacroRelationships(db);
    console.log('[macro-relationship-staleness-sweep]', { staleCount });
    return { staleCount };
  },
});
