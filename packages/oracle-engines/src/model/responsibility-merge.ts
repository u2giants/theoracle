import { createHash } from 'node:crypto';
import {
  BUSINESS_MODEL_SHAPE_REGISTRY,
  validateBusinessShapeElement,
} from '@oracle/shared/business-model-shapes';
import {
  resolveWorkflowMapNodeEntities,
  type DepartmentRegistryRow,
} from './entity-resolution';
import type { RegistryEntity } from '../extraction/entity-resolver';

export type ResponsibilityCandidate = {
  mapElementRef: string;
  claimId: string;
  label: string;
  role: string;
  action: string;
  object: string;
  trigger?: string | null;
  requiredSystem?: string | null;
  ownerName?: string | null;
  department?: string | null;
  evidenceQuote: string;
  chunkId: string;
};

export type ResponsibilityOperation = {
  type: 'add_responsibility' | 'update_responsibility' | 'remove_responsibility';
  targetElementKey?: string;
  sourceElementRef: string;
  evidenceClaimId: string;
  fields: Pick<
    ResponsibilityCandidate,
    'label' | 'role' | 'action' | 'object' | 'trigger' | 'requiredSystem'
  >;
};

export type ResponsibilityMergeVerdict = {
  verdict: 'create_object' | 'confirm' | 'refine_object' | 'contradict' | 'needs_review';
  proposedName: string;
  proposedSlug: string;
  summary: string;
  operations: ResponsibilityOperation[];
  targetObjectId?: string | null;
  omittedSourceElementRefs: Array<{ sourceElementRef: string; reason: string }>;
  candidateObjectIds?: string[];
};

export function normalizeResponsibilityPart(value: string): string {
  return value
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

export function responsibilitySemanticKey(
  item: Pick<ResponsibilityCandidate, 'role' | 'action' | 'object' | 'trigger' | 'requiredSystem'>,
): string {
  return [
    item.role,
    item.action,
    item.object,
    item.trigger ?? '',
    item.requiredSystem ?? '',
  ]
    .map(normalizeResponsibilityPart)
    .join('|');
}

export function responsibilityProposalInputHash(input: {
  sourceMapId: string;
  baseVersionId: string | null;
  promptVersion: string;
  modelVersion: string;
  candidates: readonly ResponsibilityCandidate[];
}): string {
  return createHash('sha256')
    .update(
      JSON.stringify({
        sourceMapId: input.sourceMapId,
        baseVersionId: input.baseVersionId,
        promptVersion: input.promptVersion,
        modelVersion: input.modelVersion,
        candidates: input.candidates.map((candidate) => ({
          ref: candidate.mapElementRef,
          claimId: candidate.claimId,
          semanticKey: responsibilitySemanticKey(candidate),
        })),
      }),
    )
    .digest('hex');
}

export function normalizedResponsibilitySlug(name: string): string {
  const slug = normalizeResponsibilityPart(name).replace(/\s+/g, '-').slice(0, 150);
  if (!slug) throw new Error('Responsibility object name cannot produce an empty slug.');
  return slug;
}

export function validateResponsibilityCandidates(
  candidates: readonly ResponsibilityCandidate[],
): string[] {
  const errors: string[] = [];
  const refs = new Set<string>();
  const claimIds = new Set<string>();
  for (const candidate of candidates) {
    if (refs.has(candidate.mapElementRef)) errors.push(`duplicate map ref ${candidate.mapElementRef}`);
    refs.add(candidate.mapElementRef);
    if (claimIds.has(candidate.claimId)) errors.push(`duplicate claim ${candidate.claimId}`);
    claimIds.add(candidate.claimId);
    if (!candidate.mapElementRef.includes(':element:')) {
      errors.push(`invalid responsibility map ref ${candidate.mapElementRef}`);
    }
    const detail = validateBusinessShapeElement({
      shape: 'responsibilities',
      elementKind: 'responsibility',
      detail: {
        role: candidate.role,
        action: candidate.action,
        object: candidate.object,
        ...(candidate.trigger ? { trigger: candidate.trigger } : {}),
        ...(candidate.requiredSystem ? { requiredSystem: candidate.requiredSystem } : {}),
      },
    });
    errors.push(...detail.errors.map((error) => `${candidate.mapElementRef}: ${error}`));
    if (!candidate.evidenceQuote.trim()) errors.push(`${candidate.mapElementRef}: evidence is required`);
  }
  return errors;
}

export function enforceResponsibilityCreateGuard(args: {
  verdict: ResponsibilityMergeVerdict;
  exactNamespaceObjectId?: string | null;
  plausibleObjectIds?: readonly string[];
}): ResponsibilityMergeVerdict {
  if (args.verdict.verdict !== 'create_object') return args.verdict;
  const candidates = [
    ...(args.exactNamespaceObjectId ? [args.exactNamespaceObjectId] : []),
    ...(args.plausibleObjectIds ?? []),
  ].filter((value, index, all) => all.indexOf(value) === index);
  if (candidates.length === 0) return args.verdict;
  return {
    ...args.verdict,
    verdict: 'needs_review',
    operations: [],
    omittedSourceElementRefs: args.verdict.omittedSourceElementRefs,
    candidateObjectIds: candidates,
    summary: `${args.verdict.summary} Creation blocked because a plausible responsibility model already exists.`,
  };
}

export function validateResponsibilityVerdict(args: {
  verdict: ResponsibilityMergeVerdict;
  candidates: readonly ResponsibilityCandidate[];
  durableElementKeys?: ReadonlySet<string>;
}): string[] {
  const errors = validateResponsibilityCandidates(args.candidates);
  const byRef = new Map(args.candidates.map((item) => [item.mapElementRef, item]));
  const omitted = new Set(args.verdict.omittedSourceElementRefs.map((item) => item.sourceElementRef));
  for (const item of args.verdict.omittedSourceElementRefs) {
    if (!byRef.has(item.sourceElementRef)) errors.push(`omission cites unknown source ${item.sourceElementRef}`);
  }
  if (
    args.verdict.proposedSlug !== normalizedResponsibilitySlug(args.verdict.proposedName)
  ) {
    errors.push('proposed slug is not the normalized authoritative namespace');
  }
  if (args.verdict.verdict === 'confirm' && args.verdict.operations.length > 0) {
    errors.push('confirm cannot contain structural operations');
  }
  if (args.verdict.verdict === 'create_object' && args.verdict.targetObjectId) {
    errors.push('create_object cannot target an existing object');
  }
  if (
    (args.verdict.verdict === 'needs_review' || args.verdict.verdict === 'contradict') &&
    args.verdict.operations.length > 0
  ) {
    errors.push(`${args.verdict.verdict} cannot contain applicable operations`);
  }
  for (const operation of args.verdict.operations) {
    const source = byRef.get(operation.sourceElementRef);
    if (!source) errors.push(`operation cites unknown source ${operation.sourceElementRef}`);
    if (source?.claimId !== operation.evidenceClaimId) {
      errors.push(`operation claim does not support ${operation.sourceElementRef}`);
    }
    if (
      operation.type !== 'add_responsibility' &&
      (!operation.targetElementKey || !args.durableElementKeys?.has(operation.targetElementKey))
    ) {
      errors.push(`operation cites unknown durable key ${operation.targetElementKey ?? '(missing)'}`);
    }
    if (args.verdict.verdict === 'create_object' && operation.type !== 'add_responsibility') {
      errors.push('create_object may contain only add_responsibility operations');
    }
    if (
      (operation.type === 'add_responsibility' || operation.type === 'update_responsibility') &&
      source
    ) {
      const expected = {
        label: source.label,
        role: source.role,
        action: source.action,
        object: source.object,
        trigger: source.trigger ?? null,
        requiredSystem: source.requiredSystem ?? null,
      };
      const actual = {
        label: operation.fields.label,
        role: operation.fields.role,
        action: operation.fields.action,
        object: operation.fields.object,
        trigger: operation.fields.trigger ?? null,
        requiredSystem: operation.fields.requiredSystem ?? null,
      };
      if (JSON.stringify(actual) !== JSON.stringify(expected)) {
        errors.push(`operation fields do not match evidenced source ${operation.sourceElementRef}`);
      }
    }
  }
  if (args.verdict.verdict === 'create_object') {
    const disposition = new Set([
      ...args.verdict.operations.map((operation) => operation.sourceElementRef),
      ...omitted,
    ]);
    for (const candidate of args.candidates) {
      if (!disposition.has(candidate.mapElementRef)) {
        errors.push(`create verdict does not dispose ${candidate.mapElementRef}`);
      }
    }
  }
  return errors;
}

export const RESPONSIBILITY_MERGE_PROMPT_FRAGMENT =
  BUSINESS_MODEL_SHAPE_REGISTRY.responsibilities.mergePromptFragment;

export function resolveResponsibilityCandidateEntities(args: {
  mapId: string;
  candidate: ResponsibilityCandidate;
  modelRunId?: string | null;
  entityRegistry: readonly RegistryEntity[];
  departmentRegistry?: readonly DepartmentRegistryRow[];
}) {
  return resolveWorkflowMapNodeEntities({
    mapId: args.mapId,
    modelRunId: args.modelRunId,
    nodeKey: args.candidate.mapElementRef,
    ownerName: args.candidate.ownerName ?? args.candidate.department ?? args.candidate.role,
    systems: args.candidate.requiredSystem ? [args.candidate.requiredSystem] : [],
    chunkId: args.candidate.chunkId,
    entityRegistry: args.entityRegistry,
    departmentRegistry: args.departmentRegistry,
  });
}
