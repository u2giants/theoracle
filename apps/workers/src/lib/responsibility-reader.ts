import type {
  ResponsibilityReadOutput,
  SourceStructureElement,
  SourceStructureSegment,
} from '@oracle/ai';
import { createHash } from 'node:crypto';
import {
  alternateSourceQuotePolicies,
  quoteSourceKindForDocument,
  quoteValidationOptionsForSource,
  resolveSourceQuotePolicy,
  validateQuote,
} from '@oracle/engines';
import {
  BUSINESS_MODEL_SHAPE_REGISTRY,
  validateBusinessShapeElement,
} from '@oracle/shared/business-model-shapes';

export type ResponsibilityChunk = {
  id: string;
  documentId: string;
  rawText: string;
};

export type ResponsibilityReaderDiagnostic = {
  responsibilityId: string;
  chunkId: string;
  failureClass:
    | 'duplicate_id'
    | 'unknown_chunk'
    | 'foreign_chunk'
    | 'uncovered_chunk'
    | 'quote_mismatch'
    | 'invalid_detail';
  detail: string;
  boundedQuote: string;
  selectedPolicy: string;
  validationMethod: string;
  alternatePoliciesPassing: string[];
  crossSegmentStatus: 'within_segment' | 'covered_same_document' | 'foreign' | 'uncovered';
  failureOrigin: 'root';
};

export function responsibilityMapElementRef(mapId: string, elementId: string): string {
  return `${mapId}:element:${elementId}`;
}

export function validateResponsibilityRead(args: {
  output: ResponsibilityReadOutput;
  documentId: string;
  segment: SourceStructureSegment;
  chunks: readonly ResponsibilityChunk[];
  fileType?: string | null;
  fileName?: string | null;
  allCoveredChunkIds?: ReadonlySet<string>;
}): {
  elements: SourceStructureElement[];
  diagnostics: ResponsibilityReaderDiagnostic[];
  crossSegmentCitations: Array<{ responsibilityId: string; chunkId: string }>;
  primaryCount: number;
} {
  const diagnostics: ResponsibilityReaderDiagnostic[] = [];
  const elements: SourceStructureElement[] = [];
  const crossSegmentCitations: Array<{ responsibilityId: string; chunkId: string }> = [];
  const byId = new Map(args.chunks.map((chunk) => [chunk.id, chunk]));
  const covered = new Set(args.segment.chunkIds);
  const allCovered = args.allCoveredChunkIds ?? covered;
  const seen = new Set<string>();
  const sourceKind = quoteSourceKindForDocument({
    fileType: args.fileType ?? '',
    fileName: args.fileName ?? '',
  });
  const policy = resolveSourceQuotePolicy(sourceKind);

  for (const record of args.output.responsibilities) {
    const base = {
      responsibilityId: record.responsibilityId,
      chunkId: record.chunkId,
      boundedQuote: record.evidenceQuote.slice(0, 240),
      selectedPolicy: policy.name,
      validationMethod: 'none',
      alternatePoliciesPassing: [] as string[],
      crossSegmentStatus: 'within_segment' as const,
      failureOrigin: 'root' as const,
    };
    if (seen.has(record.responsibilityId)) {
      diagnostics.push({ ...base, failureClass: 'duplicate_id', detail: 'ID is duplicated.' });
      continue;
    }
    seen.add(record.responsibilityId);
    const chunk = byId.get(record.chunkId);
    if (!chunk) {
      diagnostics.push({ ...base, failureClass: 'unknown_chunk', detail: 'Chunk does not exist.' });
      continue;
    }
    if (chunk.documentId !== args.documentId) {
      diagnostics.push({
        ...base,
        failureClass: 'foreign_chunk',
        detail: 'Chunk belongs to another document.',
        crossSegmentStatus: 'foreign',
      });
      continue;
    }
    if (!allCovered.has(chunk.id)) {
      diagnostics.push({
        ...base,
        failureClass: 'uncovered_chunk',
        detail: 'Chunk is not covered anywhere in this document segmentation.',
        crossSegmentStatus: 'uncovered',
      });
      continue;
    }
    const quote = validateQuote({
      sourceText: chunk.rawText,
      exactQuoteProvided: record.evidenceQuote,
      ...quoteValidationOptionsForSource(sourceKind),
    });
    if (!['exact_match', 'normalized_match'].includes(quote.validationStatus)) {
      const alternatePoliciesPassing = alternateSourceQuotePolicies(policy.name)
        .filter((alternate) => {
          const result = validateQuote({
            sourceText: chunk.rawText,
            exactQuoteProvided: record.evidenceQuote,
            normalizationPolicy: alternate.normalizationPolicy,
            allowFuzzy: alternate.allowFuzzy,
            fuzzyMinOverlap: alternate.fuzzyMinOverlap,
          });
          return ['exact_match', 'normalized_match'].includes(result.validationStatus);
        })
        .map((alternate) => alternate.name);
      diagnostics.push({
        ...base,
        failureClass: 'quote_mismatch',
        detail: `Quote failed deterministic policy ${policy.name}.`,
        validationMethod: quote.validationMethod,
        alternatePoliciesPassing,
        crossSegmentStatus: covered.has(chunk.id)
          ? 'within_segment'
          : 'covered_same_document',
      });
      continue;
    }
    const detail = validateBusinessShapeElement({
      shape: 'responsibilities',
      elementKind: 'responsibility',
      detail: {
        role: record.role,
        action: record.action,
        object: record.object,
        ...(record.trigger ? { trigger: record.trigger } : {}),
        ...(record.requiredSystem ? { requiredSystem: record.requiredSystem } : {}),
      },
    });
    if (detail.errors.length > 0) {
      diagnostics.push({
        ...base,
        failureClass: 'invalid_detail',
        detail: detail.errors.join('; '),
      });
      continue;
    }
    if (!covered.has(chunk.id)) {
      crossSegmentCitations.push({
        responsibilityId: record.responsibilityId,
        chunkId: record.chunkId,
      });
    }
    elements.push({
      elementId: record.responsibilityId,
      segmentId: args.segment.segmentId,
      shape: 'responsibilities',
      elementKind: 'responsibility',
      label: record.label,
      ownerName: record.ownerName ?? null,
      department: record.department ?? null,
      role: record.role,
      action: record.action,
      object: record.object,
      trigger: record.trigger ?? null,
      system: record.requiredSystem ?? null,
      systems: record.requiredSystem ?? null,
      evidenceQuote: quote.validatedExactQuote ?? record.evidenceQuote,
      chunkId: record.chunkId,
    });
  }
  return {
    elements,
    diagnostics,
    crossSegmentCitations,
    primaryCount: elements.filter((item) =>
      BUSINESS_MODEL_SHAPE_REGISTRY.responsibilities.primaryElementKinds.includes(
        item.elementKind as 'responsibility',
      ),
    ).length,
  };
}

export function responsibilityRawAuditArtifact(output: ResponsibilityReadOutput): {
  sha256: string;
  boundedJson: string;
  truncated: boolean;
} {
  const raw = JSON.stringify(output);
  return {
    sha256: createHash('sha256').update(raw).digest('hex'),
    boundedJson: raw.slice(0, 64_000),
    truncated: raw.length > 64_000,
  };
}

export function responsibilityCoverage(args: {
  mapId: string;
  elements: readonly SourceStructureElement[];
  claimMapRefs: ReadonlySet<string>;
}): { primary: number; evidenced: number; ratio: number; missingRefs: string[] } {
  const primary = args.elements.filter(
    (item) => item.shape === 'responsibilities' && item.elementKind === 'responsibility',
  );
  const missingRefs = primary
    .map((item) => responsibilityMapElementRef(args.mapId, item.elementId))
    .filter((ref) => !args.claimMapRefs.has(ref));
  const evidenced = primary.length - missingRefs.length;
  return {
    primary: primary.length,
    evidenced,
    ratio: primary.length === 0 ? 1 : evidenced / primary.length,
    missingRefs,
  };
}
