export type MacroRelationshipStatus =
  | 'pending_review'
  | 'blocked_pending_support'
  | 'approved'
  | 'rejected'
  | 'needs_review'
  | 'stale_support'
  | 'superseded';

export type SupportClaimStatus = 'approved' | 'pending_review' | 'rejected' | 'superseded' | string;

export function allMacroSupportApproved(statuses: readonly SupportClaimStatus[]): boolean {
  return statuses.length >= 2 && statuses.every((status) => status === 'approved');
}

export function statusForGeneratedMacroRelationship(statuses: readonly SupportClaimStatus[]): MacroRelationshipStatus {
  if (statuses.length < 2) return 'needs_review';
  if (statuses.some((status) => status === 'rejected' || status === 'superseded')) {
    return 'needs_review';
  }
  // Generated macro relationships should be visible in the admin review queue
  // even while their support claims are pending. Read-time Brain/chat helpers
  // still require approved support before trusted consumption; this only avoids
  // the holistic layer disappearing behind a noisy atomic-claim queue.
  return 'pending_review';
}

export function statusAfterDroppingMacroSupport(statuses: readonly SupportClaimStatus[]): MacroRelationshipStatus {
  return allMacroSupportApproved(statuses) ? 'pending_review' : 'needs_review';
}

export function statusAfterMacroSupportChange(args: {
  currentStatus: MacroRelationshipStatus;
  supportStatuses: readonly SupportClaimStatus[];
}): MacroRelationshipStatus {
  if (args.currentStatus === 'approved' && !allMacroSupportApproved(args.supportStatuses)) {
    return 'stale_support';
  }
  if (
    (args.currentStatus === 'blocked_pending_support' || args.currentStatus === 'needs_review') &&
    allMacroSupportApproved(args.supportStatuses)
  ) {
    return 'pending_review';
  }
  return args.currentStatus;
}
