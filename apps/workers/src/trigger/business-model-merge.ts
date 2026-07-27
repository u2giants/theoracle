import { task } from '@trigger.dev/sdk/v3';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import { createResponsibilityShadowProposal } from '../lib/business-model-merge';

const payloadSchema = z.object({
  sourceMapId: z.string().uuid(),
});

export const businessModelMergeTask = task({
  id: 'business-model-merge',
  run: async (rawPayload: unknown) => {
    const payload = payloadSchema.parse(rawPayload);
    return createResponsibilityShadowProposal({
      db: getDirectDb(),
      sourceMapId: payload.sourceMapId,
    });
  },
});
