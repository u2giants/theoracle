import { z } from 'zod';

const id = z.string().min(1);

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

export type SupportedTaxonomyReclassification = keyof typeof schemas;

export function validateTaxonomyReclassificationPayload(
  proposalType: string,
  payload: unknown,
): { valid: true } | { valid: false; reason: string } {
  if (proposalType === 'split_top_domain' || proposalType === 'split_sub_topic') {
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
