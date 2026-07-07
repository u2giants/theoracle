import { task } from '@trigger.dev/sdk/v3';
import { z } from 'zod';
import { generateSourceWorkflowMap } from '../lib/source-workflow-read';

const payloadSchema = z.object({
  documentId: z.string().uuid(),
  force: z.boolean().optional(),
});

export const sourceWorkflowReadTask = task({
  id: 'source-workflow-read',
  run: async (rawPayload: unknown, { ctx }) => {
    const payload = payloadSchema.parse(rawPayload);
    return generateSourceWorkflowMap({
      documentId: payload.documentId,
      force: payload.force ?? false,
      triggerRunId: ctx.run.id,
    });
  },
});
