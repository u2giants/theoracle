import type { Department, EntityType } from '@oracle/shared';
import { DEPARTMENTS } from '@oracle/shared';
import { canonicalizeSummary } from '../extraction/candidate-hash';
import {
  resolveEntity,
  type RegistryEntity,
  type ResolveEntityResult,
} from '../extraction/entity-resolver';
import type { StageEntityProposalArgs } from '../extraction/stage-entity-proposal';

export interface DepartmentRegistryRow {
  id: Department;
  displayLabel?: string | null;
}

export interface WorkflowMapEntityResolutionInput {
  mapId: string;
  modelRunId?: string | null;
  nodeKey: string;
  ownerName?: string | null;
  systems?: readonly (string | null | undefined)[] | null;
  chunkId?: string | null;
  entityRegistry: readonly RegistryEntity[];
  departmentRegistry?: readonly DepartmentRegistryRow[];
}

export interface UnresolvedWorkflowMapEntity {
  rawString: string;
  proposedEntityType: EntityType;
  role: 'owner' | 'system';
  reason: 'unknown' | 'type_mismatch' | 'ambiguous' | 'missing_source_chunk';
  matchedEntityId?: string;
  matchedEntityType?: EntityType;
  candidateEntityIds?: string[];
}

export interface ResolvedWorkflowMapEntityRefs {
  ownerDepartmentId: Department | null;
  ownerEntityId: string | null;
  ownerRaw: string | null;
  systemEntityIds: string[];
  unresolved: UnresolvedWorkflowMapEntity[];
  entityProposalsToStage: StageEntityProposalArgs[];
}

const DEFAULT_OWNER_ENTITY_TYPES: readonly EntityType[] = [
  'person',
  'department',
  'vendor',
  'service_provider',
  'factory',
  'freight_provider',
  'testing_lab',
  'packaging_supplier',
];

function normalizeRaw(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function defaultDepartmentRegistry(): DepartmentRegistryRow[] {
  return DEPARTMENTS.map((id) => ({
    id,
    displayLabel: id.replace(/_/g, ' '),
  }));
}

function resolveDepartment(
  raw: string,
  departments: readonly DepartmentRegistryRow[],
): Department | null {
  const normalizedRaw = canonicalizeSummary(raw);
  const matches = departments.filter((department) => {
    const labels = [department.id, department.displayLabel].filter(Boolean) as string[];
    return labels.some((label) => canonicalizeSummary(label) === normalizedRaw);
  });

  return matches.length === 1 ? matches[0]!.id : null;
}

function proposalFor(
  input: WorkflowMapEntityResolutionInput,
  rawString: string,
  proposedEntityType: EntityType,
): StageEntityProposalArgs | null {
  if (!input.chunkId) return null;
  return {
    proposedEntityType,
    proposedCanonicalValue: rawString.trim(),
    rawString,
    observedInSourceType: 'document_chunk',
    observedInSourceId: input.chunkId,
    proposedByModelRunId: input.modelRunId ?? null,
  };
}

function unresolvedFromResult(
  role: 'owner' | 'system',
  rawString: string,
  proposedEntityType: EntityType,
  result: Exclude<ResolveEntityResult, { outcome: 'resolved' }>,
  hasSourceChunk: boolean,
): UnresolvedWorkflowMapEntity {
  if (!hasSourceChunk && result.outcome === 'unknown') {
    return {
      role,
      rawString,
      proposedEntityType,
      reason: 'missing_source_chunk',
    };
  }

  if (result.outcome === 'type_mismatch') {
    return {
      role,
      rawString,
      proposedEntityType,
      reason: 'type_mismatch',
      matchedEntityId: result.matchedEntityId,
      matchedEntityType: result.matchedEntityType,
    };
  }

  if (result.outcome === 'ambiguous') {
    return {
      role,
      rawString,
      proposedEntityType,
      reason: 'ambiguous',
      candidateEntityIds: result.candidates.map((candidate) => candidate.entityId),
    };
  }

  return {
    role,
    rawString,
    proposedEntityType,
    reason: 'unknown',
  };
}

function resolveOwnerEntity(
  raw: string,
  registry: readonly RegistryEntity[],
): ResolveEntityResult {
  const resolved: Extract<ResolveEntityResult, { outcome: 'resolved' }>[] = [];
  const ambiguous: Extract<ResolveEntityResult, { outcome: 'ambiguous' }>[] = [];
  const mismatches: Extract<ResolveEntityResult, { outcome: 'type_mismatch' }>[] = [];

  for (const entityType of DEFAULT_OWNER_ENTITY_TYPES) {
    const result = resolveEntity({
      proposedEntityType: entityType,
      rawString: raw,
      registry: [...registry],
    });

    if (result.outcome === 'resolved') resolved.push(result);
    if (result.outcome === 'ambiguous') ambiguous.push(result);
    if (result.outcome === 'type_mismatch') mismatches.push(result);
  }

  const uniqueResolved = new Map(resolved.map((result) => [result.entityId, result]));
  if (uniqueResolved.size === 1) return [...uniqueResolved.values()][0]!;
  if (uniqueResolved.size > 1) {
    return {
      outcome: 'ambiguous',
      proposedEntityType: 'department',
      rawString: raw,
      candidates: [...uniqueResolved.values()].map((result) => ({
        entityId: result.entityId,
        canonicalValue: result.canonicalValue,
      })),
    };
  }

  if (ambiguous[0]) return ambiguous[0];
  if (mismatches[0]) return mismatches[0];

  return {
    outcome: 'unknown',
    proposal: {
      proposedEntityType: 'department',
      proposedCanonicalValue: raw.trim(),
      rawString: raw,
    },
  };
}

export function resolveWorkflowMapNodeEntities(
  input: WorkflowMapEntityResolutionInput,
): ResolvedWorkflowMapEntityRefs {
  const departments = input.departmentRegistry ?? defaultDepartmentRegistry();
  const unresolved: UnresolvedWorkflowMapEntity[] = [];
  const entityProposalsToStage: StageEntityProposalArgs[] = [];
  const systemEntityIds = new Set<string>();
  let ownerDepartmentId: Department | null = null;
  let ownerEntityId: string | null = null;
  let ownerRaw: string | null = null;

  const ownerName = normalizeRaw(input.ownerName);
  if (ownerName) {
    const departmentId = resolveDepartment(ownerName, departments);
    if (departmentId) {
      ownerDepartmentId = departmentId;
    } else {
      const result = resolveOwnerEntity(ownerName, input.entityRegistry);
      if (result.outcome === 'resolved') {
        ownerEntityId = result.entityId;
      } else {
        ownerRaw = ownerName;
        unresolved.push(
          unresolvedFromResult('owner', ownerName, 'department', result, Boolean(input.chunkId)),
        );
        const proposal = proposalFor(input, ownerName, 'department');
        if (proposal && result.outcome !== 'ambiguous') entityProposalsToStage.push(proposal);
      }
    }
  }

  for (const rawSystem of input.systems ?? []) {
    const systemName = normalizeRaw(rawSystem);
    if (!systemName) continue;

    const result = resolveEntity({
      proposedEntityType: 'system',
      rawString: systemName,
      registry: [...input.entityRegistry],
    });

    if (result.outcome === 'resolved') {
      systemEntityIds.add(result.entityId);
      continue;
    }

    unresolved.push(
      unresolvedFromResult('system', systemName, 'system', result, Boolean(input.chunkId)),
    );
    const proposal = proposalFor(input, systemName, 'system');
    if (proposal && result.outcome !== 'ambiguous') entityProposalsToStage.push(proposal);
  }

  return {
    ownerDepartmentId,
    ownerEntityId,
    ownerRaw,
    systemEntityIds: [...systemEntityIds],
    unresolved,
    entityProposalsToStage,
  };
}
