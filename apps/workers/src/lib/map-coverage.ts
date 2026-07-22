import { createHash } from 'node:crypto';
import {
  SOURCE_STRUCTURE_SHAPE_REGISTRY,
  type SourceStructureMap,
  type SourceStructureShape,
} from '@oracle/ai';

export type PrimaryMapRef = {
  ref: string;
  shape: SourceStructureShape;
  kind: 'element' | 'relation';
  localId: string;
  elementKind: string;
  label: string;
  segmentId: string;
  chunkId: string;
};

export type MapCoverageReconciliation = {
  mapId: string;
  primaryRefs: PrimaryMapRef[];
  coveredRefs: PrimaryMapRef[];
  omissions: PrimaryMapRef[];
  unknownClaimRefs: string[];
  duplicateClaimRefs: Array<{ ref: string; count: number }>;
  coverageByShape: Record<string, { primary: number; covered: number; coverage: number }>;
  coverage: number;
};

export function listPrimaryMapRefs(mapId: string, map: SourceStructureMap): PrimaryMapRef[] {
  const refs: PrimaryMapRef[] = [];
  for (const element of map.elements) {
    const contract = SOURCE_STRUCTURE_SHAPE_REGISTRY[element.shape];
    if (!(contract.primaryElementKinds as readonly string[]).includes(element.elementKind))
      continue;
    refs.push({
      ref: `${mapId}:element:${element.elementId}`,
      shape: element.shape,
      kind: 'element',
      localId: element.elementId,
      elementKind: element.elementKind,
      label: element.label,
      segmentId: element.segmentId,
      chunkId: element.chunkId,
    });
  }
  for (const relation of map.relations) {
    const contract = SOURCE_STRUCTURE_SHAPE_REGISTRY[relation.shape];
    if (!(contract.primaryRelationKinds as readonly string[]).includes(relation.relationKind))
      continue;
    refs.push({
      ref: `${mapId}:relation:${relation.relationId}`,
      shape: relation.shape,
      kind: 'relation',
      localId: relation.relationId,
      elementKind: relation.relationKind,
      label: `${relation.fromElementId} -> ${relation.toElementId}`,
      segmentId: relation.segmentId,
      chunkId: relation.chunkId,
    });
  }
  return refs.sort((a, b) => a.ref.localeCompare(b.ref));
}

export function reconcileMapPrimaryClaims(args: {
  mapId: string;
  map: SourceStructureMap;
  claimMapElementRefs: readonly string[];
}): MapCoverageReconciliation {
  const primaryRefs = listPrimaryMapRefs(args.mapId, args.map);
  const primaryByRef = new Map(primaryRefs.map((ref) => [ref.ref, ref]));
  const counts = new Map<string, number>();
  for (const ref of args.claimMapElementRefs) counts.set(ref, (counts.get(ref) ?? 0) + 1);
  const coveredRefs = primaryRefs.filter((ref) => counts.has(ref.ref));
  const omissions = primaryRefs.filter((ref) => !counts.has(ref.ref));
  const unknownClaimRefs = [...counts.keys()].filter((ref) => !primaryByRef.has(ref)).sort();
  const duplicateClaimRefs = [...counts.entries()]
    .filter(([, count]) => count > 1)
    .map(([ref, count]) => ({ ref, count }))
    .sort((a, b) => a.ref.localeCompare(b.ref));

  const coverageByShape: Record<string, { primary: number; covered: number; coverage: number }> =
    {};
  for (const shape of Object.keys(SOURCE_STRUCTURE_SHAPE_REGISTRY)) {
    const primary = primaryRefs.filter((ref) => ref.shape === shape).length;
    const covered = coveredRefs.filter((ref) => ref.shape === shape).length;
    coverageByShape[shape] = {
      primary,
      covered,
      coverage: primary === 0 ? 1 : covered / primary,
    };
  }
  return {
    mapId: args.mapId,
    primaryRefs,
    coveredRefs,
    omissions,
    unknownClaimRefs,
    duplicateClaimRefs,
    coverageByShape,
    coverage: primaryRefs.length === 0 ? 1 : coveredRefs.length / primaryRefs.length,
  };
}

export function modelCoverageGapId(args: {
  sourceType: 'document' | 'message';
  sourceId: string;
  mapId: string;
  mapElementRef: string;
}): string {
  const hex = createHash('sha256')
    .update(
      ['model_coverage', args.sourceType, args.sourceId, args.mapId, args.mapElementRef].join('|'),
      'utf8',
    )
    .digest('hex')
    .slice(0, 32)
    .split('');
  hex[12] = '5';
  const variant = Number.parseInt(hex[16]!, 16);
  hex[16] = ((variant & 0x3) | 0x8).toString(16);
  const value = hex.join('');
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}
