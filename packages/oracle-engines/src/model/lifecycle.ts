import { and, eq } from 'drizzle-orm';
import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db/client';
import {
  businessModelChangeEvents,
  businessModelChanges,
  businessObjects,
  businessProcesses,
  settings,
  type BusinessModelChange,
} from '@oracle/db/schema';

export const SOURCE_WORKFLOW_MAP_STATUSES = [
  'pending',
  'validated',
  'degraded',
  'failed',
  'superseded',
] as const;
export type SourceWorkflowMapStatus = (typeof SOURCE_WORKFLOW_MAP_STATUSES)[number];

export const BUSINESS_MODEL_CHANGE_STATUSES = [
  'pending_review',
  'approved',
  'rejected',
  'auto_applied',
  'needs_rebase',
  'superseded',
  'failed_apply',
] as const;
export type BusinessModelChangeStatus = (typeof BUSINESS_MODEL_CHANGE_STATUSES)[number];

export const BUSINESS_OBJECT_VERSION_STATUSES = [
  'pending_review',
  'approved',
  'superseded',
  'rejected',
] as const;
export type BusinessObjectVersionStatus = (typeof BUSINESS_OBJECT_VERSION_STATUSES)[number];
// Compatibility aliases stay until the legacy process model is removed in R10.
export const BUSINESS_PROCESS_VERSION_STATUSES = BUSINESS_OBJECT_VERSION_STATUSES;
export type BusinessProcessVersionStatus = BusinessObjectVersionStatus;

export function assertBusinessModelApplyAllowed(args: {
  settingValue: unknown;
  operationsJson?: unknown;
}): void {
  if (!(args.settingValue === true || args.settingValue === 'true')) {
    throw new Error('Business-model apply is disabled by the fail-safe setting.');
  }
  const operations = (args.operationsJson ?? {}) as {
    applyEligible?: boolean;
    shadow?: boolean;
  };
  if (operations.shadow === true || operations.applyEligible === false) {
    throw new Error('Shadow proposal is read-only and cannot be applied.');
  }
}

const MAP_TRANSITIONS = {
  pending: ['validated', 'degraded', 'failed'],
  validated: ['superseded'],
  degraded: ['superseded'],
  failed: [],
  superseded: [],
} satisfies Record<SourceWorkflowMapStatus, readonly SourceWorkflowMapStatus[]>;

const CHANGE_TRANSITIONS = {
  pending_review: ['approved', 'rejected', 'auto_applied', 'needs_rebase', 'failed_apply'],
  approved: [],
  rejected: [],
  auto_applied: [],
  needs_rebase: ['superseded'],
  superseded: [],
  failed_apply: [],
} satisfies Record<BusinessModelChangeStatus, readonly BusinessModelChangeStatus[]>;

const VERSION_TRANSITIONS = {
  pending_review: ['approved', 'rejected'],
  approved: ['superseded'],
  superseded: [],
  rejected: [],
} satisfies Record<BusinessObjectVersionStatus, readonly BusinessObjectVersionStatus[]>;

export function canTransitionSourceWorkflowMap(
  from: SourceWorkflowMapStatus,
  to: SourceWorkflowMapStatus,
): boolean {
  return MAP_TRANSITIONS[from].some((candidate) => candidate === to);
}

export function canTransitionBusinessModelChange(
  from: BusinessModelChangeStatus,
  to: BusinessModelChangeStatus,
): boolean {
  return CHANGE_TRANSITIONS[from].some((candidate) => candidate === to);
}

export function canTransitionBusinessProcessVersion(
  from: BusinessProcessVersionStatus,
  to: BusinessProcessVersionStatus,
): boolean {
  return canTransitionBusinessObjectVersion(from, to);
}

export function canTransitionBusinessObjectVersion(
  from: BusinessObjectVersionStatus,
  to: BusinessObjectVersionStatus,
): boolean {
  return VERSION_TRANSITIONS[from].some((candidate) => candidate === to);
}

export class InvalidBusinessModelTransitionError extends Error {
  constructor(entity: string, from: string, to: string) {
    super(`Invalid ${entity} transition: ${from} -> ${to}`);
    this.name = 'InvalidBusinessModelTransitionError';
  }
}

export class StaleBusinessModelProposalError extends Error {
  constructor(
    readonly proposalId: string,
    readonly targetId: string,
    readonly expectedVersionId: string | null,
    readonly actualVersionId: string | null,
  ) {
    super(
      `Business model proposal ${proposalId} is stale for object ${targetId}: expected current version ${expectedVersionId}, got ${actualVersionId}`,
    );
    this.name = 'StaleBusinessModelProposalError';
  }
}

export class BusinessModelApplyStatusError extends Error {
  constructor(readonly proposalId: string, readonly status: string) {
    super(`Business model proposal ${proposalId} cannot be applied from status ${status}`);
    this.name = 'BusinessModelApplyStatusError';
  }
}

export class InvalidBusinessModelProposalTargetError extends Error {
  constructor(readonly proposalId: string, detail: string) {
    super(`Business model proposal ${proposalId} has an invalid target: ${detail}`);
    this.name = 'InvalidBusinessModelProposalTargetError';
  }
}

export function assertBusinessModelChangeTransition(
  from: BusinessModelChangeStatus,
  to: BusinessModelChangeStatus,
): void {
  if (!canTransitionBusinessModelChange(from, to)) {
    throw new InvalidBusinessModelTransitionError('business_model_changes', from, to);
  }
}

export function businessModelAdvisoryLockKey(
  processId: string | null,
  proposalId: string,
  objectId: string | null = null,
  objectKind: string | null = null,
  proposedSlug: string | null = null,
): string {
  if (objectId) return `business_object:${objectId}`;
  if (objectKind && proposedSlug) return `business_object_namespace:${objectKind}:${proposedSlug}`;
  return processId ? `business_process:${processId}` : `business_model_change:${proposalId}`;
}

export type BusinessModelApplyTx = Parameters<Parameters<OracleDb['transaction']>[0]>[0];

export interface ApplyBusinessModelChangeArgs<T> {
  db: OracleDb;
  proposalId: string;
  reviewedByEmployeeId?: string | null;
  reviewerNote?: string | null;
  apply: (tx: BusinessModelApplyTx, proposal: BusinessModelChange) => Promise<T>;
}

export type ApplyBusinessModelChangeResult<T> =
  | { status: 'applied'; proposal: BusinessModelChange; value: T }
  | { status: 'noop'; proposal: BusinessModelChange }
  | { status: 'needs_rebase'; proposal: BusinessModelChange; actualVersionId: string | null };

export interface BusinessModelApplyPreconditionProposal {
  id: string;
  status: string;
  processId: string | null;
  baseVersionId: string | null;
  objectId?: string | null;
  baseObjectVersionId?: string | null;
}

export type BusinessModelApplyPrecondition =
  | { status: 'ready' }
  | { status: 'noop' }
  | { status: 'needs_rebase'; actualVersionId: string | null };

export function shouldMarkFailedApply(status: string | null | undefined): boolean {
  return status === 'pending_review';
}

export function evaluateBusinessModelApplyPrecondition(
  proposal: BusinessModelApplyPreconditionProposal,
  actualVersionId: string | null,
): BusinessModelApplyPrecondition {
  if (!shouldMarkFailedApply(proposal.status)) {
    return { status: 'noop' };
  }

  if (proposal.objectId && !proposal.baseObjectVersionId) {
    throw new InvalidBusinessModelProposalTargetError(
      proposal.id,
      'existing object proposals require baseObjectVersionId',
    );
  }
  if (proposal.processId && !proposal.baseVersionId) {
    throw new InvalidBusinessModelProposalTargetError(
      proposal.id,
      'existing legacy process proposals require baseVersionId',
    );
  }

  if (
    ((proposal.objectId &&
      proposal.baseObjectVersionId &&
      actualVersionId !== proposal.baseObjectVersionId) ||
      (proposal.processId &&
        proposal.baseVersionId &&
        actualVersionId !== proposal.baseVersionId))
  ) {
    return { status: 'needs_rebase', actualVersionId };
  }

  return { status: 'ready' };
}

/**
 * Stage-1 transactional skeleton for model-change approval/confirm.
 *
 * Later stages provide the `apply` callback that creates versions, typed
 * elements, relations, paths, evidence links, and audit events. This wrapper owns the
 * concurrency contract: per-object (or create namespace) advisory lock, status guard, optimistic
 * current-version check, terminal failure marking, and audit events.
 */
export async function applyBusinessModelChangeTransaction<T>({
  db,
  proposalId,
  reviewedByEmployeeId = null,
  reviewerNote = null,
  apply,
}: ApplyBusinessModelChangeArgs<T>): Promise<ApplyBusinessModelChangeResult<T>> {
  try {
    return await db.transaction(async (tx) => {
      const [applySetting] = await tx
        .select({ value: settings.value })
        .from(settings)
        .where(eq(settings.key, 'business_model_apply_enabled'))
        .limit(1);
      assertBusinessModelApplyAllowed({ settingValue: applySetting?.value });
      const [proposal] = await tx
        .select()
        .from(businessModelChanges)
        .where(eq(businessModelChanges.id, proposalId))
        .limit(1);

      if (!proposal) {
        throw new Error(`Business model proposal not found: ${proposalId}`);
      }
      assertBusinessModelApplyAllowed({
        settingValue: applySetting?.value,
        operationsJson: proposal.operationsJson,
      });

      const lockKey = businessModelAdvisoryLockKey(
        proposal.processId,
        proposal.id,
        proposal.objectId,
        proposal.objectKind,
        proposal.proposedSlug,
      );
      await tx.execute(sql`SELECT pg_advisory_xact_lock(hashtext(${lockKey}))`);

      const [lockedProposal] = await tx
        .select()
        .from(businessModelChanges)
        .where(eq(businessModelChanges.id, proposalId))
        .limit(1);

      if (!lockedProposal) {
        throw new Error(`Business model proposal not found after lock: ${proposalId}`);
      }

      if (!shouldMarkFailedApply(lockedProposal.status)) {
        return { status: 'noop', proposal: lockedProposal };
      }

      if (lockedProposal.objectId) {
        const [object] = await tx
          .select({
            id: businessObjects.id,
            currentVersionId: businessObjects.currentVersionId,
          })
          .from(businessObjects)
          .where(eq(businessObjects.id, lockedProposal.objectId))
          .limit(1);

        const actualVersionId = object?.currentVersionId ?? null;
        const precondition = evaluateBusinessModelApplyPrecondition(
          lockedProposal,
          actualVersionId,
        );
        if (precondition.status === 'needs_rebase') {
          const beforeState = lockedProposal;
          const [updated] = await tx
            .update(businessModelChanges)
            .set({ status: 'needs_rebase', updatedAt: new Date() })
            .where(
              and(
                eq(businessModelChanges.id, lockedProposal.id),
                eq(businessModelChanges.status, 'pending_review'),
              ),
            )
            .returning();

          if (!updated) {
            const [latest] = await tx
              .select()
              .from(businessModelChanges)
              .where(eq(businessModelChanges.id, lockedProposal.id))
              .limit(1);
            return { status: 'noop', proposal: latest ?? lockedProposal };
          }

          await tx.insert(businessModelChangeEvents).values({
            businessModelChangeId: lockedProposal.id,
            action: 'needs_rebase',
            reviewedByEmployeeId,
            reviewerNote,
            beforeState,
            afterState: { ...updated, actualVersionId },
          });

          return { status: 'needs_rebase', proposal: updated, actualVersionId };
        }
      } else if (lockedProposal.processId) {
        const [process] = await tx
          .select({
            id: businessProcesses.id,
            currentVersionId: businessProcesses.currentVersionId,
          })
          .from(businessProcesses)
          .where(eq(businessProcesses.id, lockedProposal.processId))
          .limit(1);

        const actualVersionId = process?.currentVersionId ?? null;
        const precondition = evaluateBusinessModelApplyPrecondition(
          lockedProposal,
          actualVersionId,
        );
        if (precondition.status === 'needs_rebase') {
          const beforeState = lockedProposal;
          const [updated] = await tx
            .update(businessModelChanges)
            .set({
              status: 'needs_rebase',
              updatedAt: new Date(),
            })
            .where(
              and(
                eq(businessModelChanges.id, lockedProposal.id),
                eq(businessModelChanges.status, 'pending_review'),
              ),
            )
            .returning();

          if (!updated) {
            const [latest] = await tx
              .select()
              .from(businessModelChanges)
              .where(eq(businessModelChanges.id, lockedProposal.id))
              .limit(1);
            return { status: 'noop', proposal: latest ?? lockedProposal };
          }

          await tx.insert(businessModelChangeEvents).values({
            businessModelChangeId: lockedProposal.id,
            action: 'needs_rebase',
            reviewedByEmployeeId,
            reviewerNote,
            beforeState,
            afterState: {
              ...(updated ?? proposal),
              actualVersionId,
            },
          });

          return {
            status: 'needs_rebase',
            proposal: updated,
            actualVersionId,
          };
        }
      }

      const value = await apply(tx, lockedProposal);
      return { status: 'applied', proposal: lockedProposal, value };
    });
  } catch (err) {
    await db
      .update(businessModelChanges)
      .set({
        status: 'failed_apply',
        updatedAt: new Date(),
      })
      .where(
        and(
          eq(businessModelChanges.id, proposalId),
          eq(businessModelChanges.status, 'pending_review'),
        ),
      );
    throw err;
  }
}
