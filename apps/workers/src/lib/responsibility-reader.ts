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

export type ResponsibilityOmission = {
  chunkId: string;
  spanIndex: number;
  sourceSpan: string;
};

const DUTY_VERBS =
  'approve|ask|assign|authorize|call|check|complete|create|download|email|ensure|enter|establish|fill|inform|keep|maintain|organize|prepare|prioritize|provide|reach|receive|record|rename|request|resubmit|review|save|send|submit|update|upload|wait|write';
const DUTY_VERB_PATTERN =
  new RegExp(`\\b(?:${DUTY_VERBS})(?:s|es|ed|ing)?\\b`, 'i');
const DUTY_VERB_START_PATTERN =
  new RegExp(`^(?:${DUTY_VERBS})(?:s|es|ed|ing)?\\b`, 'i');
const DUTY_SPLIT_PATTERN = new RegExp(
  `\\s+(?:&|and then|and(?=\\s+(?:${DUTY_VERBS})(?:s|es|ed|ing)?\\b))\\s+`,
  'i',
);
const FIELD_STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'if', 'in',
  'into', 'is', 'it', 'must', 'of', 'off', 'on', 'or', 'out', 'shall', 'should', 'so',
  'that', 'the', 'their', 'them', 'then', 'this', 'to', 'up', 'will', 'with',
]);
const ACTION_PARTICLES = new Set(['ahead', 'away', 'back', 'down', 'forward', 'off', 'on', 'out', 'over', 'through', 'up']);

function fieldTokens(value: string): string[] {
  return value
    .normalize('NFKD')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter((token) => token.length > 1 && !FIELD_STOP_WORDS.has(token));
}

function stemDutyVerb(value: string): string {
  const normalized = value.toLowerCase();
  return (
    DUTY_VERBS.split('|').find((base) =>
      new RegExp(`^${base}(?:s|es|d|ed|ing)?$`, 'i').test(normalized),
    ) ?? normalized
  );
}

function fieldAwareSpanCovered(
  sourceSpan: string,
  element: SourceStructureElement,
): boolean {
  const verbMatch = sourceSpan.match(DUTY_VERB_PATTERN);
  if (!verbMatch || verbMatch.index === undefined) return false;
  const beforeVerb = sourceSpan.slice(0, verbMatch.index);
  const afterVerb = sourceSpan.slice(verbMatch.index + verbMatch[0].length);
  const bracketOwner = sourceSpan.match(/^\s*\[([^\]]{2,80})\]/)?.[1] ?? null;
  const modalOwner =
    beforeVerb.match(/(?:^|[,;])\s*([A-Z][A-Za-z0-9 &/'-]{1,80}?)\s+(?:will|must|should|shall|may)\s*$/)?.[1] ??
    null;
  const directPrefix = beforeVerb.replace(/^(?:[-*•]|\d+[.)])\s*/, '').trim();
  const directOwner =
    /^[A-Z]/.test(directPrefix) &&
    !/^(?:if|when|after|before|at)\b/i.test(directPrefix) &&
    fieldTokens(directPrefix).length <= 6
      ? directPrefix
      : null;
  const prefixOwner = bracketOwner ?? modalOwner ?? directOwner ?? '';
  const expectedRole = fieldTokens(prefixOwner);
  const actualRole = new Set(fieldTokens(element.role ?? ''));
  if (
    expectedRole.length > 0 &&
    (expectedRole.length !== actualRole.size ||
      !expectedRole.every((token) => actualRole.has(token)))
  ) {
    return false;
  }
  const expectedAction = stemDutyVerb(verbMatch[0]);
  const actualActions = fieldTokens(element.action ?? '').map(stemDutyVerb);
  if (!actualActions.includes(expectedAction)) return false;
  const afterVerbTokens = fieldTokens(afterVerb);
  while (afterVerbTokens.length > 0 && ACTION_PARTICLES.has(afterVerbTokens[0]!)) {
    afterVerbTokens.shift();
  }
  const expectedObject = [...new Set(afterVerbTokens)];
  const actualObject = new Set(fieldTokens(element.object ?? ''));
  return expectedObject.length > 0 && expectedObject.every((token) => actualObject.has(token));
}

function dutyTextWithoutOwner(sourceSpan: string): string {
  return sourceSpan.replace(/^\s*\[[^\]]{2,80}\]\s*/, '').trim();
}

export function shardResponsibilitySegments(
  segments: readonly SourceStructureSegment[],
  chunks: readonly Pick<ResponsibilityChunk, 'id'>[],
): SourceStructureSegment[] {
  const order = new Map(chunks.map((chunk, index) => [chunk.id, index]));
  return segments.flatMap((segment) =>
    [...segment.chunkIds]
      .sort((a, b) => (order.get(a) ?? Number.MAX_SAFE_INTEGER) - (order.get(b) ?? Number.MAX_SAFE_INTEGER))
      .map((chunkId, index) => ({
        ...segment,
        segmentId: `${segment.segmentId}__chunk_${String(index + 1).padStart(3, '0')}`,
        chunkIds: [chunkId],
      })),
  );
}

export function responsibilityParentSegment(
  shard: SourceStructureSegment,
): SourceStructureSegment {
  return {
    ...shard,
    segmentId: shard.segmentId.replace(/__chunk_\d{3}$/, ''),
  };
}

export function prefixResponsibilityOutput(
  output: ResponsibilityReadOutput,
  shardIndex: number,
): ResponsibilityReadOutput {
  const prefix = `shard_${String(shardIndex + 1).padStart(3, '0')}__`;
  return prefixResponsibilityIds(output, prefix);
}

export function prefixResponsibilityRetryOutput(
  output: ResponsibilityReadOutput,
  shardIndex: number,
  attempt: number,
): ResponsibilityReadOutput {
  if (!Number.isInteger(attempt) || attempt < 1) {
    throw new Error('Responsibility retry attempt must be a positive integer.');
  }
  const prefix =
    `retry_${String(shardIndex + 1).padStart(3, '0')}_` +
    `${String(attempt).padStart(3, '0')}__`;
  return prefixResponsibilityIds(output, prefix);
}

function prefixResponsibilityIds(
  output: ResponsibilityReadOutput,
  prefix: string,
): ResponsibilityReadOutput {
  return {
    ...output,
    responsibilities: output.responsibilities.map((record) => ({
      ...record,
      responsibilityId:
        `${prefix}${record.responsibilityId}`.length <= 120
          ? `${prefix}${record.responsibilityId}`
          : `${prefix}${record.responsibilityId.slice(0, 96)}_${createHash('sha256')
              .update(record.responsibilityId)
              .digest('hex')
              .slice(0, 8)}`,
    })),
  };
}

function logicalSourceSpans(rawText: string): string[] {
  const spans: string[] = [];
  let current = '';
  const flush = () => {
    if (current.trim()) spans.push(current.trim());
    current = '';
  };
  for (const rawLine of rawText.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      flush();
      continue;
    }
    const heading = /^(?:\[[^\]]{2,80}\]|[^.!?]{2,80}:)$/.test(line);
    const explicitStart =
      heading ||
      /^(?:[-*•]|\d+[.)])\s*/.test(line) ||
      /^\[[^\]]{2,80}\]\s+/.test(line) ||
      DUTY_VERB_START_PATTERN.test(line);
    const currentIsDuty =
      /^(?:[-*•]|\d+[.)])\s*/.test(current) ||
      /^\[[^\]]{2,80}\]\s+/.test(current) ||
      DUTY_VERB_PATTERN.test(current);
    if (explicitStart) {
      flush();
      current = line;
    } else if (current && currentIsDuty && !/[.!?]$/.test(current)) {
      current = `${current} ${line}`;
    } else {
      flush();
      current = line;
    }
  }
  flush();
  return spans;
}

function sourceDutySpans(rawText: string): string[] {
  const output: string[] = [];
  let ownerHeading: string | null = null;
  for (const rawSpan of logicalSourceSpans(rawText)) {
    const trimmed = rawSpan.trim();
    if (!trimmed) continue;
    const headingMatch = trimmed.match(/^(?:\[([^\]]{2,80})\]|([^.!?]{2,80}):)$/);
    if (headingMatch) {
      ownerHeading = (headingMatch[1] ?? headingMatch[2] ?? '').trim();
      continue;
    }
    const listLike = /^(?:[-*•]|\d+[.)])\s*/.test(trimmed);
    const span = trimmed.replace(/^(?:[-*•]|\d+[.)])\s*/, '');
    const inlineOwner = /^\[[^\]]{2,80}\]\s+/.test(span);
    for (const part of span.split(DUTY_SPLIT_PATTERN).map((item) => item.trim())) {
      if (part.length < 12) continue;
      const narrative = /^(?:background|note|overview|purpose|this section)\b/i.test(part);
      const hasDutyVerb = DUTY_VERB_PATTERN.test(part);
      if (
        !narrative &&
        ((listLike && hasDutyVerb) ||
          DUTY_VERB_START_PATTERN.test(part) ||
          (inlineOwner && hasDutyVerb) ||
          (ownerHeading !== null && hasDutyVerb))
      ) {
        output.push(ownerHeading && !inlineOwner ? `[${ownerHeading}] ${part}` : part);
      }
    }
  }
  return output;
}

export function findResponsibilityOmissions(args: {
  chunks: readonly ResponsibilityChunk[];
  elements: readonly SourceStructureElement[];
  fileType?: string | null;
  fileName?: string | null;
}): ResponsibilityOmission[] {
  const sourceKind = quoteSourceKindForDocument({
    fileType: args.fileType ?? '',
    fileName: args.fileName ?? '',
  });
  const byChunk = new Map<string, SourceStructureElement[]>();
  for (const element of args.elements) {
    if (!element.chunkId || !element.evidenceQuote) continue;
    const list = byChunk.get(element.chunkId) ?? [];
    list.push(element);
    byChunk.set(element.chunkId, list);
  }
  return args.chunks.flatMap((chunk) =>
    sourceDutySpans(chunk.rawText).flatMap((sourceSpan, spanIndex) => {
      const covered = (byChunk.get(chunk.id) ?? []).some((element) => {
        const quoteWithinSpan = validateQuote({
          sourceText: sourceSpan,
          exactQuoteProvided: element.evidenceQuote!,
          ...quoteValidationOptionsForSource(sourceKind),
        });
        const spanWithinQuote = validateQuote({
          sourceText: element.evidenceQuote!,
          exactQuoteProvided: sourceSpan,
          ...quoteValidationOptionsForSource(sourceKind),
        });
        const quoteCovered = [quoteWithinSpan, spanWithinQuote].some((result) =>
          ['exact_match', 'normalized_match'].includes(result.validationStatus),
        );
        return quoteCovered && fieldAwareSpanCovered(sourceSpan, element);
      });
      return covered ? [] : [{ chunkId: chunk.id, spanIndex, sourceSpan }];
    }),
  );
}

export function assertUniqueResponsibilityElementIds(
  elements: readonly SourceStructureElement[],
): void {
  const seen = new Set<string>();
  for (const element of elements) {
    if (element.shape !== 'responsibilities') continue;
    if (seen.has(element.elementId)) {
      throw new Error(`Duplicate responsibility elementId before persistence: ${element.elementId}`);
    }
    seen.add(element.elementId);
  }
}

export function mergeResponsibilityValidationResults<T extends {
  segment: SourceStructureSegment;
  validation: {
    elements: SourceStructureElement[];
    diagnostics: ResponsibilityReaderDiagnostic[];
    crossSegmentCitations: Array<{ responsibilityId: string; chunkId: string }>;
    primaryCount: number;
  };
}>(reads: readonly T[]): T[] {
  return [...reads].sort(
    (a, b) =>
      a.segment.segmentId.localeCompare(b.segment.segmentId) ||
      (a.segment.chunkIds[0] ?? '').localeCompare(b.segment.chunkIds[0] ?? ''),
  );
}

type ResponsibilityValidation = ReturnType<typeof validateResponsibilityRead>;

export function mergeResponsibilityRetryValidation(
  base: ResponsibilityValidation,
  retry: ResponsibilityValidation,
): { validation: ResponsibilityValidation; acceptedCount: number } {
  const elementKey = (item: SourceStructureElement) =>
    `${item.chunkId}|${item.role}|${item.action}|${item.object}|${item.evidenceQuote}`;
  const existingElements = new Set(base.elements.map(elementKey));
  const accepted = retry.elements.filter((item) => !existingElements.has(elementKey(item)));
  const diagnosticKey = (item: ResponsibilityReaderDiagnostic) =>
    `${item.responsibilityId}|${item.chunkId}|${item.failureClass}|${item.boundedQuote}`;
  const existingDiagnostics = new Set(base.diagnostics.map(diagnosticKey));
  const diagnostics = retry.diagnostics.filter(
    (item) => !existingDiagnostics.has(diagnosticKey(item)),
  );
  const citationKey = (item: { responsibilityId: string; chunkId: string }) =>
    `${item.responsibilityId}|${item.chunkId}`;
  const existingCitations = new Set(base.crossSegmentCitations.map(citationKey));
  const citations = retry.crossSegmentCitations.filter(
    (item) => !existingCitations.has(citationKey(item)),
  );
  return {
    validation: {
      elements: [...base.elements, ...accepted],
      diagnostics: [...base.diagnostics, ...diagnostics],
      crossSegmentCitations: [...base.crossSegmentCitations, ...citations],
      primaryCount: base.primaryCount + accepted.length,
    },
    acceptedCount: accepted.length,
  };
}

export function patchResponsibilityQuoteRepairs(args: {
  original: ResponsibilityReadOutput;
  diagnostics: readonly ResponsibilityReaderDiagnostic[];
  repaired: ResponsibilityReadOutput;
}): { ok: true; output: ResponsibilityReadOutput } | { ok: false; reason: string } {
  const eligible = new Map(
    args.diagnostics
      .filter((item) => item.failureClass === 'quote_mismatch')
      .map((item) => [item.responsibilityId, item]),
  );
  const repairs = new Map<string, string>();
  for (const record of args.repaired.responsibilities) {
    if (repairs.has(record.responsibilityId)) return { ok: false, reason: 'duplicate_repair' };
    const diagnostic = eligible.get(record.responsibilityId);
    if (!diagnostic) return { ok: false, reason: 'unknown_or_ineligible_record' };
    const original = args.original.responsibilities.find(
      (item) => item.responsibilityId === record.responsibilityId,
    );
    if (!original || original.chunkId !== record.chunkId) {
      return { ok: false, reason: 'chunk_move' };
    }
    const { evidenceQuote: _originalQuote, ...originalFields } = original;
    const { evidenceQuote: _repairQuote, ...repairFields } = record;
    if (JSON.stringify(originalFields) !== JSON.stringify(repairFields)) {
      return { ok: false, reason: 'non_quote_field_change' };
    }
    repairs.set(record.responsibilityId, record.evidenceQuote);
  }
  if (repairs.size === 0) return { ok: false, reason: 'empty_repair' };
  return {
    ok: true,
    output: {
      ...args.original,
      responsibilities: args.original.responsibilities.map((record) => ({
        ...record,
        evidenceQuote: repairs.get(record.responsibilityId) ?? record.evidenceQuote,
      })),
    },
  };
}

export const RESPONSIBILITY_FOCUSED_OMISSION_LIMIT = 6;

export function rankResponsibilityOmissionChunks(
  omissions: readonly ResponsibilityOmission[],
  chunks: readonly Pick<ResponsibilityChunk, 'id'>[],
): Array<{ chunkId: string; omissions: ResponsibilityOmission[] }> {
  const sourceOrder = new Map(chunks.map((chunk, index) => [chunk.id, index]));
  const grouped = new Map<string, ResponsibilityOmission[]>();
  for (const omission of omissions) {
    const list = grouped.get(omission.chunkId) ?? [];
    list.push(omission);
    grouped.set(omission.chunkId, list);
  }
  return [...grouped.entries()]
    .map(([chunkId, groupedOmissions]) => ({
      chunkId,
      omissions: [...groupedOmissions].sort((a, b) => a.spanIndex - b.spanIndex),
    }))
    .sort(
      (a, b) =>
        b.omissions.length - a.omissions.length ||
        (sourceOrder.get(a.chunkId) ?? Number.MAX_SAFE_INTEGER) -
          (sourceOrder.get(b.chunkId) ?? Number.MAX_SAFE_INTEGER) ||
        a.chunkId.localeCompare(b.chunkId),
    );
}

export function selectFocusedResponsibilityOmissions(
  omissions: readonly ResponsibilityOmission[],
  limit = RESPONSIBILITY_FOCUSED_OMISSION_LIMIT,
): ResponsibilityOmission[] {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error('Focused responsibility omission limit must be a positive integer.');
  }
  return [...omissions]
    .sort(
      (a, b) =>
        Number(DUTY_VERB_START_PATTERN.test(dutyTextWithoutOwner(b.sourceSpan))) -
          Number(DUTY_VERB_START_PATTERN.test(dutyTextWithoutOwner(a.sourceSpan))) ||
        b.sourceSpan.length - a.sourceSpan.length ||
        a.spanIndex - b.spanIndex,
    )
    .slice(0, limit);
}

export type ResponsibilityOmissionRetryDecision =
  | {
      kind: 'attempt';
      chunkId: string;
      omissions: ResponsibilityOmission[];
      preOmissionCount: number;
    }
  | {
      kind: 'no_source_read';
      chunkId: string;
      omissions: ResponsibilityOmission[];
      preOmissionCount: number;
    }
  | { kind: 'done' };

export class ResponsibilityOmissionRetryScheduler {
  private readonly exhaustedChunks = new Set<string>();
  private stopped = false;

  next(args: {
    omissions: readonly ResponsibilityOmission[];
    chunks: readonly Pick<ResponsibilityChunk, 'id'>[];
    sourceReadChunkIds: ReadonlySet<string>;
  }): ResponsibilityOmissionRetryDecision {
    if (this.stopped) return { kind: 'done' };
    const next = rankResponsibilityOmissionChunks(args.omissions, args.chunks).find(
      (item) => !this.exhaustedChunks.has(item.chunkId),
    );
    if (!next) return { kind: 'done' };
    const decision = {
      chunkId: next.chunkId,
      omissions: selectFocusedResponsibilityOmissions(next.omissions),
      preOmissionCount: args.omissions.length,
    };
    if (!args.sourceReadChunkIds.has(next.chunkId)) {
      this.exhaustedChunks.add(next.chunkId);
      return { kind: 'no_source_read', ...decision };
    }
    return { kind: 'attempt', ...decision };
  }

  recordAttempt(
    chunkId: string,
    outcome: 'accepted' | 'zero_accept' | 'retry_failed' | 'budget_exhausted',
  ): void {
    this.exhaustedChunks.add(chunkId);
    if (outcome === 'budget_exhausted') this.stopped = true;
  }
}

export function buildResponsibilityOmissionAudit<T extends {
  preOmissionCount: number;
  postOmissionCount: number;
}>(args: {
  initialOmissions: readonly ResponsibilityOmission[];
  finalOmissions: readonly ResponsibilityOmission[];
  retries: readonly T[];
}) {
  return {
    preOmissionCount: args.initialOmissions.length,
    postOmissionCount: args.finalOmissions.length,
    uncoveredSpanCount: args.finalOmissions.length,
    retries: [...args.retries],
  };
}

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
