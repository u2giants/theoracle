import { z } from 'zod';

const id = z.string().min(1);

export const SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES = [
  'create_sub_topic',
  'reassign_claims',
  'merge_sub_topics',
  'retire_sub_topic',
  'merge_top_domains',
] as const;

export const MANUAL_TAXONOMY_RECLASSIFICATION_TYPES = [
  'split_top_domain',
  'split_sub_topic',
] as const;

const schemas = {
  create_sub_topic: z.object({
    topDomainId: id,
    proposedName: z.string().trim().min(1),
    oneSentencePurpose: z.string().optional(),
    clusterCentroid: z.array(z.number()).optional(),
    representativeClaimIds: z.array(id).optional(),
  }),
  reassign_claims: z
    .object({
      fromSubTopicId: id,
      toSubTopicId: id,
      claimIds: z.array(id).optional(),
    })
    .refine((p) => p.fromSubTopicId !== p.toSubTopicId, 'source and target must differ'),
  merge_sub_topics: z
    .object({ sourceSubTopicId: id, targetSubTopicId: id })
    .refine((p) => p.sourceSubTopicId !== p.targetSubTopicId, 'source and target must differ'),
  retire_sub_topic: z.object({ subTopicId: id }),
  merge_top_domains: z
    .object({ sourceTopDomainId: id, targetTopDomainId: id })
    .refine((p) => p.sourceTopDomainId !== p.targetTopDomainId, 'source and target must differ'),
} as const;

export type SupportedTaxonomyReclassification =
  (typeof SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES)[number];

export function validateTaxonomyReclassificationPayload(
  proposalType: string,
  payload: unknown,
): { valid: true } | { valid: false; reason: string } {
  if ((MANUAL_TAXONOMY_RECLASSIFICATION_TYPES as readonly string[]).includes(proposalType)) {
    return { valid: false, reason: `${proposalType} requires manual admin intervention` };
  }
  const schema = schemas[proposalType as SupportedTaxonomyReclassification];
  if (!schema) return { valid: false, reason: `unknown proposal type: ${proposalType}` };
  const result = schema.safeParse(payload);
  return result.success
    ? { valid: true }
    : {
        valid: false,
        reason: `invalid payload: ${result.error.issues[0]?.message ?? 'unknown error'}`,
      };
}

export function isTerminalReclassificationChange(changeType: string): boolean {
  return (
    changeType.startsWith('reclassification_applied_') ||
    changeType.startsWith('reclassification_skipped_')
  );
}

export function classifyTaxonomyProposalState(input: {
  proposalType: string;
  status: string;
  latestChangeType: string | null;
  hasQueuedAudit: boolean;
}): string {
  if (input.status !== 'approved') return input.status;
  if (input.proposalType === 'create_top_domain') return 'applied_inline';
  if (input.latestChangeType?.startsWith('reclassification_applied_')) return 'applied';
  if (input.latestChangeType?.startsWith('reclassification_skipped_')) return 'skipped';
  if (input.latestChangeType === 'reclassification_failed') return 'failed';
  if (input.latestChangeType === 'reclassification_dispatched') return 'applying';
  return input.hasQueuedAudit ? 'queued' : 'approved_not_queued';
}

export function isActionableTaxonomyProposalState(state: string): boolean {
  return ['approved_not_queued', 'queued', 'applying', 'failed'].includes(state);
}
