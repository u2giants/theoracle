import { eq } from 'drizzle-orm';
import {
  extractionBatches,
  messages,
  type OracleDb,
} from '@oracle/db';

type OwnerStatus = {
  status: string;
  error?: string | null;
};

export type MessageExtractionTerminalDecision =
  | { status: 'complete' }
  | { status: 'failed'; error: string }
  | { status: 'processing' };

/**
 * A successful owner is sticky. A message fails only after every staged owner
 * in this extraction run has failed. Non-terminal owners keep it processing.
 * `failed_validation_loop` remains complete because its source window was
 * successfully received and deterministically processed; its candidates and
 * validation audit are the durable result, matching the pre-window behavior.
 */
export function decideMessageExtractionStatus(
  owners: OwnerStatus[],
): MessageExtractionTerminalDecision {
  if (owners.some((owner) =>
    owner.status === 'validation_complete' || owner.status === 'failed_validation_loop'
  )) {
    return { status: 'complete' };
  }
  if (owners.length > 0 && owners.every((owner) => owner.status === 'failed')) {
    return {
      status: 'failed',
      error:
        owners.map((owner) => owner.error).filter(Boolean).join('; ') ||
        'Every extraction window containing this message failed.',
    };
  }
  return { status: 'processing' };
}

export async function reconcileMessageExtractionStatuses(args: {
  db: OracleDb;
  jobRunId: string;
  messageIds: string[];
}): Promise<void> {
  const uniqueMessageIds = [...new Set(args.messageIds)];
  if (uniqueMessageIds.length === 0) return;
  const ownerRows = await args.db
    .select({
      sourceMessageIds: extractionBatches.sourceMessageIds,
      status: extractionBatches.status,
      error: extractionBatches.error,
    })
    .from(extractionBatches)
    .where(eq(extractionBatches.jobRunId, args.jobRunId));

  for (const messageId of uniqueMessageIds) {
    const owners = ownerRows
      .filter((row) =>
        Array.isArray(row.sourceMessageIds) &&
        row.sourceMessageIds.some((id) => id === messageId)
      )
      .map((row) => ({ status: row.status, error: row.error }));
    const decision = decideMessageExtractionStatus(owners);
    if (decision.status === 'complete') {
      await args.db
        .update(messages)
        .set({
          extractionStatus: 'complete',
          extractionError: null,
          extractedAt: new Date(),
        })
        .where(eq(messages.id, messageId));
    } else if (decision.status === 'failed') {
      await args.db
        .update(messages)
        .set({
          extractionStatus: 'failed',
          extractionError: decision.error,
        })
        .where(eq(messages.id, messageId));
    }
  }
}
