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
  evidenceQuote?: string;
  sourceStart?: number;
  sourceEnd?: number;
  sourceLocationFailure?: string;
  listStructured?: boolean;
};

export type ResponsibilitySpanRankFeatures = {
  verbStartsSpan: boolean;
  explicitOwner: boolean;
  listStructured: boolean;
  concreteTokenCount: number;
  sourceLength: number;
  chunkOmissionCount: number;
  sourceChunkIndex: number;
};

export type RankedResponsibilityOmission = ResponsibilityOmission & {
  rankIndex: number;
  rankFeatures: ResponsibilitySpanRankFeatures;
  sourceSpanSha256: string;
};

export type ForcedResponsibilitySpan = RankedResponsibilityOmission & {
  forcedResponsibilityId: string;
  evidenceQuote: string;
  sourceStart: number;
  sourceEnd: number;
};

export type ResponsibilityFieldFidelityResult = {
  passed: boolean;
  reasons: string[];
  sourceDutyVerbs: string[];
  returnedActionVerbs: string[];
  polarityFailure: boolean;
  multiVerbReject: boolean;
};

export type ResponsibilityFailureCategory =
  | 'field'
  | 'quote'
  | 'multi_verb'
  | 'forced_missing'
  | 'invalid_detail';

export type ResponsibilityIncompleteAudit = {
  elementId: string;
  chunkId: string;
  failureCategory: ResponsibilityFailureCategory;
  repairStatus: 'not_selected' | 'selected' | 'repaired' | 'rejected';
  decisionReason: string;
  quoteSha256: string;
  selectedSourceSpan: string;
};

export type ResponsibilityExpansionAudit = {
  baseId: string;
  expandedId: string;
  destination: string;
  accepted: boolean;
  reason: string;
};

export type GroundedResponsibilityQuoteCandidate = {
  candidateIndex: number;
  sourceText: string;
  sourceTextSha256: string;
  tokenOverlap: number;
};

const DUTY_VERBS =
  'approve|archive|ask|assign|authorize|call|check|complete|coordinate|create|download|email|ensure|enter|establish|fill|inform|keep|maintain|manage|monitor|organize|prepare|prioritize|provide|publish|reach|receive|record|rename|report|request|resubmit|review|save|send|submit|track|update|upload|verify|wait|write';
const DUTY_VERB_PATTERN =
  new RegExp(`\\b(?:${DUTY_VERBS})(?:s|es|ed|ing)?\\b`, 'i');
const DUTY_VERB_START_PATTERN =
  new RegExp(`^(?:${DUTY_VERBS})(?:s|es|ed|ing)?\\b`, 'i');
const MODAL_OR_DIRECT_OWNER_PATTERN = new RegExp(
  `^[A-Z][A-Za-z0-9 &/'-]{1,80}?\\s+(?:(?:will|must|should|shall|may)\\s+)?(?:${DUTY_VERBS})(?:s|es|ed|ing)?\\b`,
  'i',
);
const DUTY_SPLIT_PATTERN = new RegExp(
  `(?:\\s+(?:&|and then|then|and)\\s+|\\s*[,;]\\s*)(?=(?:${DUTY_VERBS})(?:s|es|d|ed|ing)?\\b)`,
  'i',
);
const FIELD_STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'if', 'in',
  'into', 'is', 'it', 'must', 'of', 'off', 'on', 'or', 'out', 'shall', 'should', 'so',
  'that', 'the', 'their', 'them', 'then', 'this', 'to', 'up', 'will', 'with',
]);
const ACTION_PARTICLES = new Set(['ahead', 'away', 'back', 'down', 'forward', 'off', 'on', 'out', 'over', 'through', 'up']);
const OUTBOUND_DUTY_VERBS = new Set(['provide', 'send', 'submit', 'email', 'upload', 'publish', 'inform', 'report']);
const INBOUND_DUTY_VERBS = new Set(['receive', 'get', 'obtain', 'download']);

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
      [
        base,
        `${base}s`,
        `${base}es`,
        `${base}d`,
        `${base}ed`,
        `${base}ing`,
        ...(base.endsWith('e') ? [`${base.slice(0, -1)}ing`] : []),
      ].includes(normalized),
    ) ?? normalized
  );
}

function dutyVerbsInText(value: string): string[] {
  const dutyVerbs = new Set(DUTY_VERBS.split('|'));
  return value
    .normalize('NFKD')
    .toLowerCase()
    .match(/[a-z]+/g)
    ?.map(stemDutyVerb)
    .filter((token) => dutyVerbs.has(token)) ?? [];
}

function dutyVerbsInSourceSpan(value: string): string[] {
  const first = sourceDutyVerbMatch(value);
  if (!first) return [];
  const verbs = [stemDutyVerb(first.text)];
  const continuationPattern = new RegExp(
    `(?:\\b(?:and|then)\\b|[;&,])\\s+((?:${DUTY_VERBS})(?:s|es|d|ed|ing)?)\\b`,
    'gi',
  );
  for (const match of value.slice(first.index + first.text.length).matchAll(continuationPattern)) {
    if (match[1]) verbs.push(stemDutyVerb(match[1]));
  }
  return verbs;
}

function fidelityTokens(value: string): string[] {
  const rawTokens = value
    .normalize('NFKD')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .match(/[a-z0-9]+/g) ?? [];
  const markerLabels = new Set(['form', 'id', 'route', 'type']);
  return rawTokens
    .filter((token, index) =>
      !FIELD_STOP_WORDS.has(token) ||
      (token.length === 1 && markerLabels.has(rawTokens[index - 1] ?? '')),
    )
    .map((token) => {
      const dutyStem = stemDutyVerb(token);
      if (dutyStem !== token) return dutyStem;
      if (token.length > 3 && /ies$/.test(token)) return `${token.slice(0, -3)}y`;
      if (
        token.length > 3 &&
        /s$/.test(token) &&
        !/(?:ss|us|is|status)$/.test(token)
      ) {
        return token.slice(0, -1);
      }
      return token;
    });
}

function sourceDutyVerbMatch(sourceSpan: string): { text: string; index: number } | null {
  const bracketPrefix = sourceSpan.match(/^\s*\[[^\]]{2,80}\]\s*/)?.[0] ?? '';
  const body = sourceSpan.slice(bracketPrefix.length);
  const firstWord = body.match(/^[A-Za-z]+/)?.[0] ?? '';
  const ambiguousOwnerWord =
    /s$/i.test(firstWord) &&
    DUTY_VERBS.split('|').includes(stemDutyVerb(firstWord));
  const ownerLed =
    bracketPrefix || (DUTY_VERB_START_PATTERN.test(body) && !ambiguousOwnerWord)
      ? undefined
      : body.match(MODAL_OR_DIRECT_OWNER_PATTERN)?.[0];
  const searchText = ownerLed ?? body;
  const matches = [...searchText.matchAll(new RegExp(DUTY_VERB_PATTERN.source, 'gi'))];
  const selected = ownerLed ? matches.at(-1) : matches[0];
  return selected?.index === undefined
    ? null
    : {
        text: selected[0],
        index: bracketPrefix.length + selected.index,
      };
}

function sourceObjectText(sourceSpan: string): string {
  const verbMatch = sourceDutyVerbMatch(sourceSpan);
  return !verbMatch
    ? ''
    : sourceSpan.slice(verbMatch.index + verbMatch.text.length);
}

export function validateResponsibilityFieldFidelity(
  sourceSpan: string,
  element: Pick<SourceStructureElement, 'role' | 'action' | 'object'>,
): ResponsibilityFieldFidelityResult {
  const reasons: string[] = [];
  const verbMatch = sourceDutyVerbMatch(sourceSpan);
  const sourceDutyVerbs = dutyVerbsInSourceSpan(sourceSpan);
  const returnedActionVerbs = dutyVerbsInText(element.action ?? '');
  if (!verbMatch || sourceDutyVerbs.length === 0) {
    return {
      passed: false,
      reasons: ['source_has_no_duty_verb'],
      sourceDutyVerbs,
      returnedActionVerbs,
      polarityFailure: false,
      multiVerbReject: false,
    };
  }
  const beforeVerb = sourceSpan.slice(0, verbMatch.index);
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
    reasons.push('owner_mismatch');
  }
  const expectedAction = sourceDutyVerbs[0]!;
  if (!returnedActionVerbs.includes(expectedAction)) reasons.push('action_family_mismatch');
  const polarityFailure =
    (OUTBOUND_DUTY_VERBS.has(expectedAction) &&
      returnedActionVerbs.some((verb) => INBOUND_DUTY_VERBS.has(verb))) ||
    (INBOUND_DUTY_VERBS.has(expectedAction) &&
      returnedActionVerbs.some((verb) => OUTBOUND_DUTY_VERBS.has(verb)));
  if (polarityFailure) reasons.push('polarity_reversal');
  const afterVerbTokens = fidelityTokens(sourceObjectText(sourceSpan));
  while (afterVerbTokens.length > 0 && ACTION_PARTICLES.has(afterVerbTokens[0]!)) {
    afterVerbTokens.shift();
  }
  const expectedObject = [...new Set(afterVerbTokens)];
  const actualObjectTokens = fidelityTokens(element.object ?? '');
  const actualObject = new Set(actualObjectTokens);
  const sourceTokens = new Set(fidelityTokens(sourceSpan));
  const missingObjectTokens = expectedObject.filter((token) => !actualObject.has(token));
  if (missingObjectTokens.length > 0) {
    reasons.push(`object_qualifier_loss:${missingObjectTokens.join(',')}`);
  }
  const inventedObjectTokens = [...new Set(actualObjectTokens.filter((token) => !sourceTokens.has(token)))];
  if (inventedObjectTokens.length > 0) {
    reasons.push(`invented_object_content:${inventedObjectTokens.join(',')}`);
  }
  const multiVerbReject = sourceDutyVerbs.length > 1;
  if (multiVerbReject) reasons.push('unrepresented_multi_verb_duty');
  return {
    passed: reasons.length === 0,
    reasons,
    sourceDutyVerbs,
    returnedActionVerbs,
    polarityFailure,
    multiVerbReject,
  };
}

function fieldAwareSpanCovered(
  sourceSpan: string,
  element: SourceStructureElement,
): boolean {
  return validateResponsibilityFieldFidelity(sourceSpan, element).passed;
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

export function buildSyntheticResponsibilitySegments(args: {
  chunks: readonly ResponsibilityChunk[];
  existingSegments: readonly SourceStructureSegment[];
}): SourceStructureSegment[] {
  const baseReadChunkIds = new Set(args.existingSegments.flatMap((segment) => segment.chunkIds));
  return args.chunks.flatMap((chunk, index) => {
    if (baseReadChunkIds.has(chunk.id) || sourceDutySpans(chunk.rawText).length === 0) return [];
    return [{
      segmentId: `responsibility_duty_chunk_${String(index + 1).padStart(3, '0')}`,
      title: 'Deterministic duty-bearing source chunk',
      summary: 'Synthetic responsibility base read created from deterministic duty-span evidence.',
      shape: 'responsibilities' as const,
      chunkIds: [chunk.id],
    }];
  });
}

export function assertResponsibilityDutyChunksHaveBaseReads(args: {
  chunks: readonly ResponsibilityChunk[];
  baseReadSegments: readonly SourceStructureSegment[];
}): void {
  const baseReadChunkIds = new Set(args.baseReadSegments.flatMap((segment) => segment.chunkIds));
  const missing = args.chunks
    .filter((chunk) => sourceDutySpans(chunk.rawText).length > 0 && !baseReadChunkIds.has(chunk.id))
    .map((chunk) => chunk.id);
  if (missing.length > 0) {
    throw new Error(
      `Responsibility duty chunks missing base reads: ${missing.sort().join(', ')}`,
    );
  }
}

export function buildResponsibilityBaseReadPlan(args: {
  chunks: readonly ResponsibilityChunk[];
  responsibilitySegments: readonly SourceStructureSegment[];
}): {
  responsibilityShards: SourceStructureSegment[];
  syntheticSegments: SourceStructureSegment[];
  durableSegments: SourceStructureSegment[];
  syntheticBaseReadCount: number;
} {
  const segmented = shardResponsibilitySegments(args.responsibilitySegments, args.chunks);
  const syntheticSegments = buildSyntheticResponsibilitySegments({
    chunks: args.chunks,
    existingSegments: segmented,
  });
  const responsibilityShards = [...segmented, ...syntheticSegments];
  assertResponsibilityDutyChunksHaveBaseReads({
    chunks: args.chunks,
    baseReadSegments: responsibilityShards,
  });
  const seen = new Set<string>();
  const durableSegments = [...args.responsibilitySegments, ...syntheticSegments].filter(
    (segment) => {
      if (seen.has(segment.segmentId)) return false;
      seen.add(segment.segmentId);
      return true;
    },
  );
  return {
    responsibilityShards,
    syntheticSegments,
    durableSegments,
    syntheticBaseReadCount: syntheticSegments.length,
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

export function locateResponsibilityRawSlice(
  rawText: string,
  value: string,
  searchStart = 0,
): { evidenceQuote: string; sourceStart: number; sourceEnd: number } {
  const exactStart = rawText.indexOf(value, searchStart);
  if (exactStart >= 0) {
    return {
      evidenceQuote: rawText.slice(exactStart, exactStart + value.length),
      sourceStart: exactStart,
      sourceEnd: exactStart + value.length,
    };
  }
  const pattern = value
    .split(/\s+/)
    .map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('\\s+');
  const match = new RegExp(pattern, 'm').exec(rawText.slice(searchStart));
  if (match?.index === undefined) {
    throw new Error(
      `Responsibility duty span could not be bound to raw source at offset ${searchStart}: ${value.slice(0, 240)}`,
    );
  }
  const sourceStart = searchStart + match.index;
  return {
    evidenceQuote: match[0],
    sourceStart,
    sourceEnd: sourceStart + match[0].length,
  };
}

function sourceDutySpanDetails(rawText: string): Array<{
  sourceSpan: string;
  evidenceQuote?: string;
  sourceStart?: number;
  sourceEnd?: number;
  sourceLocationFailure?: string;
  listStructured: boolean;
}> {
  const output: Array<{
    sourceSpan: string;
    evidenceQuote?: string;
    sourceStart?: number;
    sourceEnd?: number;
    sourceLocationFailure?: string;
    listStructured: boolean;
  }> = [];
  let rawSearchCursor = 0;
  const locateRawSlice = (value: string): {
    evidenceQuote?: string;
    sourceStart?: number;
    sourceEnd?: number;
    sourceLocationFailure?: string;
  } => {
    try {
      const located = locateResponsibilityRawSlice(rawText, value, rawSearchCursor);
      rawSearchCursor = located.sourceEnd;
      return located;
    } catch (error) {
      return {
        sourceLocationFailure:
          error instanceof Error ? error.message : 'Responsibility raw source binding failed.',
      };
    }
  };
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
    const proseOwner = MODAL_OR_DIRECT_OWNER_PATTERN.test(span);
    const inlineOwnerLabel = span.match(/^\[([^\]]{2,80})\]/)?.[1]?.trim() ?? null;
    const proseDuty = proseOwner ? sourceDutyVerbMatch(span) : null;
    const proseOwnerLabel =
      proseDuty && proseDuty.index > 0
        ? span.slice(0, proseDuty.index).replace(/\b(?:will|must|should|shall|may)\s*$/i, '').trim()
        : null;
    const inheritedOwner = inlineOwnerLabel ?? proseOwnerLabel ?? ownerHeading;
    for (const [partIndex, rawPart] of span.split(DUTY_SPLIT_PATTERN).entries()) {
      const part = rawPart.trim();
      const narrative = /^(?:background|note|overview|purpose|this (?:section|review|document|summary))\b/i.test(part);
      const hasDutyVerb = DUTY_VERB_PATTERN.test(part);
      if (part.length < 12 && !hasDutyVerb) continue;
      if (
        !narrative &&
        ((listLike && hasDutyVerb) ||
          DUTY_VERB_START_PATTERN.test(part) ||
          (inlineOwner && hasDutyVerb) ||
          (proseOwner && hasDutyVerb) ||
          (ownerHeading !== null && hasDutyVerb))
      ) {
        const rawSlice = locateRawSlice(part);
        output.push({
            sourceSpan:
              inheritedOwner && (partIndex > 0 || (!inlineOwner && ownerHeading))
                ? `[${inheritedOwner}] ${part}`
                : part,
            ...rawSlice,
            listStructured: listLike,
          });
      }
    }
  }
  return output;
}

export function sourceDutySpans(rawText: string): string[] {
  return sourceDutySpanDetails(rawText).map((item) => item.sourceSpan);
}

export function responsibilitySpanRankFeatures(
  omission: ResponsibilityOmission,
): ResponsibilitySpanRankFeatures {
  const dutyText = dutyTextWithoutOwner(omission.sourceSpan);
  return {
    verbStartsSpan: DUTY_VERB_START_PATTERN.test(dutyText),
    explicitOwner:
      /^\s*\[[^\]]{2,80}\]/.test(omission.sourceSpan) ||
      /^[A-Z][A-Za-z0-9 &/'-]{1,80}?\s+(?:will|must|should|shall|may)\b/.test(dutyText),
    listStructured: omission.listStructured ?? false,
    concreteTokenCount: fieldTokens(dutyText).length,
    sourceLength: omission.sourceSpan.length,
    chunkOmissionCount: 0,
    sourceChunkIndex: -1,
  };
}

export function responsibilitySpanSha256(sourceSpan: string): string {
  return createHash('sha256').update(sourceSpan).digest('hex');
}

export function bindForcedResponsibilitySpans(
  selected: readonly RankedResponsibilityOmission[],
): ForcedResponsibilitySpan[] {
  const seen = new Set<string>();
  return selected.map((item) => {
    if (
      !item.evidenceQuote ||
      item.sourceStart === undefined ||
      item.sourceEnd === undefined ||
      item.sourceStart < 0 ||
      item.sourceEnd <= item.sourceStart
    ) {
      throw new Error(
        `Forced responsibility span is missing a valid raw evidence binding: ${item.chunkId}:${item.spanIndex}`,
      );
    }
    const identity = `${item.chunkId}:${item.spanIndex}:${item.sourceSpanSha256}`;
    const hash = createHash('sha256').update(identity).digest('hex').slice(0, 20);
    const forcedResponsibilityId = `forced_span_${String(item.spanIndex).padStart(4, '0')}_${hash}`;
    if (seen.has(forcedResponsibilityId)) {
      throw new Error(`Duplicate forced responsibility span ID: ${forcedResponsibilityId}`);
    }
    seen.add(forcedResponsibilityId);
    return {
      ...item,
      evidenceQuote: item.evidenceQuote,
      sourceStart: item.sourceStart,
      sourceEnd: item.sourceEnd,
      forcedResponsibilityId,
    };
  });
}

export function canonicalizeForcedResponsibilityOutput(args: {
  output: ResponsibilityReadOutput;
  selected: readonly ForcedResponsibilitySpan[];
}): {
  output: ResponsibilityReadOutput;
  audits: Array<{
    forcedResponsibilityId: string;
    chunkId: string;
    spanIndex: number;
    sourceSpanSha256: string;
    evidenceQuoteSha256: string;
    sourceStart: number;
    sourceEnd: number;
    returnedRao: ResponsibilityReadOutput['responsibilities'][number] | null;
    exactQuoteBinding: boolean;
    fieldFidelity: ResponsibilityFieldFidelityResult;
    accepted: boolean;
    rejectionReasons: string[];
  }>;
} {
  const byId = new Map<string, ResponsibilityReadOutput['responsibilities'][number][]>();
  for (const record of args.output.responsibilities) {
    const records = byId.get(record.responsibilityId) ?? [];
    records.push(record);
    byId.set(record.responsibilityId, records);
  }
  const accepted: ResponsibilityReadOutput['responsibilities'] = [];
  const audits = args.selected.map((span) => {
    const returned = byId.get(span.forcedResponsibilityId) ?? [];
    const record = returned.length === 1 ? returned[0]! : null;
    const canonical = record
      ? {
          ...record,
          responsibilityId: span.forcedResponsibilityId,
          chunkId: span.chunkId,
          evidenceQuote: span.evidenceQuote,
        }
      : null;
    const fieldFidelity = canonical
      ? validateResponsibilityFieldFidelity(span.sourceSpan, canonical)
      : {
          passed: false,
          reasons: ['missing_or_duplicate_span_record'],
          sourceDutyVerbs: dutyVerbsInSourceSpan(span.sourceSpan),
          returnedActionVerbs: [],
          polarityFailure: false,
          multiVerbReject: false,
        };
    const rejectionReasons = [
      ...(returned.length === 0 ? ['missing_span_record'] : []),
      ...(returned.length > 1 ? ['duplicate_span_record'] : []),
      ...(record && record.chunkId !== span.chunkId ? ['chunk_binding_mismatch'] : []),
      ...fieldFidelity.reasons,
    ];
    const acceptedRecord = canonical && rejectionReasons.length === 0 ? canonical : null;
    if (acceptedRecord) accepted.push(acceptedRecord);
    return {
      forcedResponsibilityId: span.forcedResponsibilityId,
      chunkId: span.chunkId,
      spanIndex: span.spanIndex,
      sourceSpanSha256: span.sourceSpanSha256,
      evidenceQuoteSha256: responsibilitySpanSha256(span.evidenceQuote),
      sourceStart: span.sourceStart,
      sourceEnd: span.sourceEnd,
      returnedRao: canonical,
      exactQuoteBinding: false,
      fieldFidelity,
      accepted: false,
      rejectionReasons,
    };
  });
  return {
    output: { ...args.output, responsibilities: accepted },
    audits,
  };
}

export function finalizeForcedResponsibilityAudits(args: {
  audits: ReturnType<typeof canonicalizeForcedResponsibilityOutput>['audits'];
  selected: readonly ForcedResponsibilitySpan[];
  durableAcceptedElementIds: ReadonlySet<string>;
  validation: ResponsibilityValidation;
  chunks: readonly ResponsibilityChunk[];
  fileType?: string | null;
  fileName?: string | null;
}): ReturnType<typeof canonicalizeForcedResponsibilityOutput>['audits'] {
  const selectedById = new Map(args.selected.map((span) => [span.forcedResponsibilityId, span]));
  const chunksById = new Map(args.chunks.map((chunk) => [chunk.id, chunk]));
  const sourceKind = quoteSourceKindForDocument({
    fileType: args.fileType ?? '',
    fileName: args.fileName ?? '',
  });
  return args.audits.map((audit) => {
    const span = selectedById.get(audit.forcedResponsibilityId);
    const chunk = chunksById.get(audit.chunkId);
    const strictQuote = span && chunk
      ? validateQuote({
          sourceText: chunk.rawText,
          exactQuoteProvided: span.evidenceQuote,
          ...quoteValidationOptionsForSource(sourceKind),
        })
      : null;
    const accepted =
      args.durableAcceptedElementIds.has(audit.forcedResponsibilityId) &&
      !args.validation.diagnostics.some(
        (item) => item.responsibilityId === audit.forcedResponsibilityId,
      );
    return {
      ...audit,
      exactQuoteBinding:
        accepted &&
        Boolean(strictQuote) &&
        ['exact_match', 'normalized_match'].includes(strictQuote!.validationStatus),
      accepted,
      rejectionReasons: accepted
        ? []
        : [
            ...audit.rejectionReasons,
            ...args.validation.diagnostics
              .filter((item) => item.responsibilityId === audit.forcedResponsibilityId)
              .map((item) => `${item.failureClass}:${item.detail}`),
            ...(audit.rejectionReasons.length === 0 &&
            !args.validation.diagnostics.some(
              (item) => item.responsibilityId === audit.forcedResponsibilityId,
            )
              ? ['not_durably_accepted']
              : []),
          ],
    };
  });
}

export function buildGroundedResponsibilityQuoteCandidates(args: {
  rawText: string;
  failedQuote: string;
  maxCandidates?: number;
}): GroundedResponsibilityQuoteCandidate[] {
  const maxCandidates = args.maxCandidates ?? 12;
  if (!Number.isInteger(maxCandidates) || maxCandidates < 1 || maxCandidates > 30) {
    throw new Error('Grounded responsibility quote candidate limit must be between 1 and 30.');
  }
  const failedTokens = new Set(fieldTokens(args.failedQuote));
  const seen = new Set<string>();
  const logical = logicalSourceSpans(args.rawText);
  const candidateSpans = logical.flatMap((sourceText, sourceIndex) => {
    const failedTerms = [...failedTokens];
    const lower = sourceText.toLowerCase();
    const hit = failedTerms.map((term) => lower.indexOf(term)).find((index) => index >= 0);
    const nearby =
      hit === undefined
        ? []
        : [sourceText.slice(Math.max(0, hit - 240), Math.min(sourceText.length, hit + 760)).trim()];
    return [sourceText, ...sourceDutySpans(sourceText), ...nearby].map((text, localIndex) => ({
      sourceText: text,
      sourceIndex: sourceIndex * 100 + localIndex,
    }));
  });
  return candidateSpans
    .map(({ sourceText, sourceIndex }) => {
      const bounded = sourceText.slice(0, 2000);
      const tokens = new Set(fieldTokens(bounded));
      const tokenOverlap = [...failedTokens].filter((token) => tokens.has(token)).length;
      return { sourceText: bounded, sourceIndex, tokenOverlap };
    })
    .filter((item) => item.sourceText.length >= 3 && item.tokenOverlap > 0)
    .sort((a, b) => b.tokenOverlap - a.tokenOverlap || a.sourceIndex - b.sourceIndex)
    .filter((item) => {
      if (seen.has(item.sourceText)) return false;
      seen.add(item.sourceText);
      return true;
    })
    .slice(0, maxCandidates)
    .map((item, candidateIndex) => ({
      candidateIndex,
      sourceText: item.sourceText,
      sourceTextSha256: responsibilitySpanSha256(item.sourceText),
      tokenOverlap: item.tokenOverlap,
    }));
}

export function validateGroundedResponsibilityQuoteSelections(args: {
  repairs: readonly Pick<
    ResponsibilityReadOutput['responsibilities'][number],
    'responsibilityId' | 'evidenceQuote'
  >[];
  offered: readonly {
    responsibilityId: string;
    candidates: readonly GroundedResponsibilityQuoteCandidate[];
  }[];
}): { ok: true } | { ok: false; responsibilityId: string } {
  const candidatesById = new Map(
    args.offered.map((item) => [
      item.responsibilityId,
      new Set(item.candidates.map((candidate) => candidate.sourceText)),
    ]),
  );
  const ungrounded = args.repairs.find(
    (repair) => !candidatesById.get(repair.responsibilityId)?.has(repair.evidenceQuote),
  );
  return ungrounded
    ? { ok: false, responsibilityId: ungrounded.responsibilityId }
    : { ok: true };
}

export function resolveEnclosingResponsibilityDutySpan(args: {
  rawText: string;
  evidenceQuote: string;
  fileType?: string | null;
  fileName?: string | null;
}): string | null {
  const sourceKind = quoteSourceKindForDocument({
    fileType: args.fileType ?? '',
    fileName: args.fileName ?? '',
  });
  const match = sourceDutySpanDetails(args.rawText).find((span) => {
    if (!span.evidenceQuote) return false;
    const quoteWithinDuty = validateQuote({
      sourceText: span.evidenceQuote,
      exactQuoteProvided: args.evidenceQuote,
      ...quoteValidationOptionsForSource(sourceKind),
    });
    const dutyWithinQuote = validateQuote({
      sourceText: args.evidenceQuote,
      exactQuoteProvided: span.evidenceQuote,
      ...quoteValidationOptionsForSource(sourceKind),
    });
    return [quoteWithinDuty, dutyWithinQuote].some((result) =>
      ['exact_match', 'normalized_match'].includes(result.validationStatus),
    );
  });
  if (match) return match.sourceSpan;
  return sourceDutyVerbMatch(args.evidenceQuote) ? args.evidenceQuote : null;
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
    sourceDutySpanDetails(chunk.rawText).flatMap<ResponsibilityOmission>((span, spanIndex) => {
      const {
        sourceSpan,
        evidenceQuote,
        sourceStart,
        sourceEnd,
        sourceLocationFailure,
        listStructured,
      } = span;
      if (!evidenceQuote || sourceStart === undefined || sourceEnd === undefined) {
        return [{
          chunkId: chunk.id,
          spanIndex,
          sourceSpan,
          listStructured,
          sourceLocationFailure: sourceLocationFailure ?? 'Responsibility raw source binding failed.',
        }];
      }
      const covered = (byChunk.get(chunk.id) ?? []).some((element) => {
        const quoteWithinSpan = validateQuote({
          sourceText: evidenceQuote,
          exactQuoteProvided: element.evidenceQuote!,
          ...quoteValidationOptionsForSource(sourceKind),
        });
        const spanWithinQuote = validateQuote({
          sourceText: element.evidenceQuote!,
          exactQuoteProvided: evidenceQuote,
          ...quoteValidationOptionsForSource(sourceKind),
        });
        const quoteCovered = [quoteWithinSpan, spanWithinQuote].some((result) =>
          ['exact_match', 'normalized_match'].includes(result.validationStatus),
        );
        return quoteCovered && fieldAwareSpanCovered(sourceSpan, element);
      });
      return covered
        ? []
        : [{
            chunkId: chunk.id,
            spanIndex,
            sourceSpan,
            evidenceQuote,
            sourceStart,
            sourceEnd,
            sourceLocationFailure,
            listStructured,
          }];
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
    inventoryElements: SourceStructureElement[];
    completeElementIds: string[];
    fieldDiagnostics: Record<string, ResponsibilityFieldFidelityResult>;
    incompleteInventoryAudit: ResponsibilityIncompleteAudit[];
    expansionAudit: ResponsibilityExpansionAudit[];
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

type LegacyResponsibilityValidation = Pick<
  ResponsibilityValidation,
  'elements' | 'diagnostics' | 'crossSegmentCitations' | 'primaryCount'
> & Partial<Omit<ResponsibilityValidation, 'elements' | 'diagnostics' | 'crossSegmentCitations' | 'primaryCount'>>;

export function mergeResponsibilityRetryValidation(
  base: LegacyResponsibilityValidation,
  retry: LegacyResponsibilityValidation,
): {
  validation: ResponsibilityValidation;
  acceptedCount: number;
  acceptedElementIds: string[];
} {
  const elementKey = (item: SourceStructureElement) =>
    `${item.chunkId}|${item.role}|${item.action}|${item.object}|${item.evidenceQuote}`;
  const existingElements = new Set(base.elements.map(elementKey));
  const accepted = retry.elements.filter((item) => !existingElements.has(elementKey(item)));
  const baseInventory = base.inventoryElements ?? base.elements;
  const retryInventory = retry.inventoryElements ?? retry.elements;
  const existingInventory = new Set(baseInventory.map(elementKey));
  const acceptedInventory = retryInventory.filter(
    (item) => !existingInventory.has(elementKey(item)),
  );
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
      inventoryElements: [...baseInventory, ...acceptedInventory],
      completeElementIds: [
        ...new Set([
          ...(base.completeElementIds ?? base.elements.map((item) => item.elementId)),
          ...(retry.completeElementIds ?? retry.elements.map((item) => item.elementId)),
        ]),
      ],
      fieldDiagnostics: { ...(base.fieldDiagnostics ?? {}), ...(retry.fieldDiagnostics ?? {}) },
      incompleteInventoryAudit: [
        ...new Map(
          [
            ...(base.incompleteInventoryAudit ?? []),
            ...(retry.incompleteInventoryAudit ?? []),
          ].map((item) => [
            item.elementId,
            item,
          ]),
        ).values(),
      ],
      expansionAudit: [...(base.expansionAudit ?? []), ...(retry.expansionAudit ?? [])],
      diagnostics: [...base.diagnostics, ...diagnostics],
      crossSegmentCitations: [...base.crossSegmentCitations, ...citations],
      primaryCount: base.primaryCount + accepted.length,
    },
    acceptedCount: accepted.length,
    acceptedElementIds: accepted.map((item) => item.elementId),
  };
}

export function responsibilityMergeEligibleElements(
  validation: ResponsibilityValidation,
): SourceStructureElement[] {
  const inventoryIds = new Set(validation.inventoryElements.map((item) => item.elementId));
  for (const id of validation.completeElementIds) {
    if (!inventoryIds.has(id)) {
      throw new Error(`Complete responsibility is absent from inventory: ${id}`);
    }
  }
  return validation.elements.filter((item) => validation.completeElementIds.includes(item.elementId));
}

export function responsibilityFailureTaxonomyCounts(
  validation: Pick<
    ResponsibilityValidation,
    'diagnostics' | 'incompleteInventoryAudit'
  >,
): Record<ResponsibilityFailureCategory, number> {
  const counts: Record<ResponsibilityFailureCategory, number> = {
    field: 0,
    quote: 0,
    multi_verb: 0,
    forced_missing: 0,
    invalid_detail: 0,
  };
  for (const audit of validation.incompleteInventoryAudit) {
    counts[audit.failureCategory] += 1;
  }
  for (const diagnostic of validation.diagnostics) {
    if (diagnostic.failureClass === 'quote_mismatch') counts.quote += 1;
    else if (
      diagnostic.failureClass === 'invalid_detail' &&
      !diagnostic.detail.startsWith('Field fidelity failed:')
    ) counts.invalid_detail += 1;
  }
  return counts;
}

function normalizedDestination(value: string): string {
  return value.normalize('NFKD').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

const DESTINATION_DIRECTED_ACTIONS = new Set([
  'archive',
  'email',
  'enter',
  'provide',
  'publish',
  'record',
  'save',
  'send',
  'submit',
  'upload',
]);
const WEAK_DESTINATION_PREPOSITIONS = new Set(['in', 'on']);
const DATE_OR_TIME_MEMBER_PATTERN =
  /^(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{1,4}(?:[/-]\d{1,2})*)$/i;

function destinationSpecificResponsibilitySpan(
  sourceSpan: string,
  destination: string,
): string {
  return sourceSpan.replace(
    /\b(to|into|in|on|via|through)\s+([^.;:\n]{2,240}?(?:,\s*[^.;:\n]+)+(?:,\s*)?(?:and|or)\s+[^.;:\n]+|[^.;:\n]+,\s*[^.;:\n]+\s+(?:and|or)\s+[^.;:\n]+|[^,.;:\n]+\s+(?:and|or)\s+[^.;:\n]+)([.;]?)(?:\s|$)/i,
    (_full, preposition: string, _list: string, punctuation: string) =>
      `${preposition} ${destination}${punctuation}`,
  );
}

export function expandResponsibilityDestinations(args: {
  sourceSpan: string;
  record: ResponsibilityReadOutput['responsibilities'][number];
}): {
  records: ResponsibilityReadOutput['responsibilities'];
  audit: ResponsibilityExpansionAudit[];
} {
  const match = args.sourceSpan.match(
    /\b(to|into|in|on|via|through)\s+([^.;:\n]{2,240}?(?:,\s*[^.;:\n]+)+(?:,\s*)?(?:and|or)\s+[^.;:\n]+|[^.;:\n]+,\s*[^.;:\n]+\s+(?:and|or)\s+[^.;:\n]+|[^,.;:\n]+\s+(?:and|or)\s+[^.;:\n]+)[.;]?(?:\s|$)/i,
  );
  if (!match?.[2]) return { records: [], audit: [] };
  const rawList = match[2].trim();
  const destinations = rawList
    .split(/\s*,\s*|\s+(?:and|or)\s+/i)
    .map((item) =>
      item.replace(/^(?:and|or)\s+/i, '').replace(/[.;]+$/, '').trim(),
    )
    .filter(Boolean);
  if (destinations.length < 2) return { records: [], audit: [] };
  const normalized = destinations.map(normalizedDestination);
  if (new Set(normalized).size !== normalized.length) {
    throw new Error(`Duplicate normalized destination for ${args.record.responsibilityId}`);
  }
  const preposition = match[1]!.toLowerCase();
  const action = dutyVerbsInText(args.record.action)[0];
  const looksLikePersonList = destinations.every((destination) =>
    /^[A-Z][a-z]{2,}$/.test(destination),
  );
  if (
    !action ||
    !DESTINATION_DIRECTED_ACTIONS.has(action) ||
    (WEAK_DESTINATION_PREPOSITIONS.has(preposition) &&
      !['archive', 'enter', 'publish', 'record', 'save', 'submit', 'upload'].includes(action)) ||
    destinations.some((destination) => DATE_OR_TIME_MEMBER_PATTERN.test(destination)) ||
    looksLikePersonList
  ) {
    return {
      records: [],
      audit: destinations.map((destination) => ({
        baseId: args.record.responsibilityId,
        expandedId: '',
        destination,
        accepted: false,
        reason: 'ambiguous_non_destination_list',
      })),
    };
  }
  const objectHead = args.record.object
    .replace(new RegExp(`\\s+${preposition}\\s+.+$`, 'i'), '')
    .trim();
  if (!objectHead || objectHead === args.record.object.trim()) {
    return {
      records: [],
      audit: destinations.map((destination) => ({
        baseId: args.record.responsibilityId,
        expandedId: '',
        destination,
        accepted: false,
        reason: 'object_head_not_source_bound',
      })),
    };
  }
  const records = destinations.map((destination, index) => {
    const hash = createHash('sha256')
      .update(`${args.record.responsibilityId}|${normalized[index]}`)
      .digest('hex')
      .slice(0, 16);
    return {
      ...args.record,
      responsibilityId: `${args.record.responsibilityId}_dst_${hash}`,
      object: `${objectHead} ${preposition} ${destination}`,
      requiredSystem:
        ['archive', 'enter', 'publish', 'record', 'save', 'submit', 'upload'].includes(action)
          ? destination
          : null,
    };
  });
  return {
    records,
    audit: records.map((record, index) => ({
      baseId: args.record.responsibilityId,
      expandedId: record.responsibilityId,
      destination: destinations[index]!,
      accepted: true,
      reason: 'explicit_coordinated_destination',
    })),
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

export function patchCombinedResponsibilityRepairs(args: {
  original: ResponsibilityReadOutput;
  fieldRequests: readonly {
    responsibilityId: string;
    chunkId: string;
    evidenceQuote: string;
    sourceSpan: string;
    allowedFields: readonly ('role' | 'action' | 'object' | 'trigger' | 'requiredSystem')[];
  }[];
  quoteRequests: readonly {
    responsibilityId: string;
    candidates: readonly { candidateId: string; sourceText: string }[];
  }[];
  repaired: {
    fieldRepairs: readonly (Partial<Pick<
      ResponsibilityReadOutput['responsibilities'][number],
      'role' | 'action' | 'object' | 'trigger' | 'requiredSystem'
    >> & { responsibilityId: string })[];
    quoteRepairs: readonly { responsibilityId: string; candidateId: string }[];
  };
}): { ok: true; output: ResponsibilityReadOutput } | { ok: false; reason: string } {
  const fieldRequests = new Map(args.fieldRequests.map((item) => [item.responsibilityId, item]));
  const quoteRequests = new Map(args.quoteRequests.map((item) => [item.responsibilityId, item]));
  const fieldRepairs = new Map<string, (typeof args.repaired.fieldRepairs)[number]>();
  for (const repair of args.repaired.fieldRepairs) {
    if (fieldRepairs.has(repair.responsibilityId)) return { ok: false, reason: 'duplicate_field_repair' };
    const request = fieldRequests.get(repair.responsibilityId);
    if (!request) return { ok: false, reason: 'unrequested_field_repair' };
    const original = args.original.responsibilities.find(
      (item) => item.responsibilityId === repair.responsibilityId,
    );
    if (
      !original ||
      original.chunkId !== request.chunkId ||
      original.evidenceQuote !== request.evidenceQuote
    ) return { ok: false, reason: 'immutable_field_binding_changed' };
    for (const [key, value] of Object.entries(repair)) {
      if (key === 'responsibilityId') continue;
      if (!request.allowedFields.includes(key as never)) {
        return { ok: false, reason: 'field_not_allowed' };
      }
      if (value != null && !request.sourceSpan.toLowerCase().includes(String(value).toLowerCase())) {
        return { ok: false, reason: 'invented_field_content' };
      }
    }
    fieldRepairs.set(repair.responsibilityId, repair);
  }
  const quoteRepairs = new Map<string, string>();
  for (const repair of args.repaired.quoteRepairs) {
    if (quoteRepairs.has(repair.responsibilityId)) return { ok: false, reason: 'duplicate_quote_repair' };
    const request = quoteRequests.get(repair.responsibilityId);
    if (!request) return { ok: false, reason: 'unrequested_quote_repair' };
    const candidate = request.candidates.find((item) => item.candidateId === repair.candidateId);
    if (!candidate) return { ok: false, reason: 'quote_not_offered' };
    quoteRepairs.set(repair.responsibilityId, candidate.sourceText);
  }
  if (fieldRepairs.size !== fieldRequests.size) {
    return { ok: false, reason: 'missing_field_repair' };
  }
  if (quoteRepairs.size !== quoteRequests.size) {
    return { ok: false, reason: 'missing_quote_repair' };
  }
  if (fieldRepairs.size + quoteRepairs.size === 0) return { ok: false, reason: 'empty_repair' };
  return {
    ok: true,
    output: {
      ...args.original,
      responsibilities: args.original.responsibilities.map((record) => ({
        ...record,
        ...(fieldRepairs.get(record.responsibilityId) ?? {}),
        evidenceQuote: quoteRepairs.get(record.responsibilityId) ?? record.evidenceQuote,
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
): RankedResponsibilityOmission[] {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error('Focused responsibility omission limit must be a positive integer.');
  }
  return [...omissions]
    .map((omission) => ({ omission, features: responsibilitySpanRankFeatures(omission) }))
    .sort(
      (a, b) =>
        Number(b.features.listStructured) - Number(a.features.listStructured) ||
        Number(b.features.verbStartsSpan) - Number(a.features.verbStartsSpan) ||
        Number(b.features.explicitOwner) - Number(a.features.explicitOwner) ||
        a.features.sourceLength - b.features.sourceLength ||
        a.omission.spanIndex - b.omission.spanIndex,
    )
    .slice(0, limit)
    .map(({ omission, features }, rankIndex) => ({
      ...omission,
      rankIndex,
      rankFeatures: features,
      sourceSpanSha256: responsibilitySpanSha256(omission.sourceSpan),
    }));
}

export type ResponsibilityOmissionRetryDecision =
  | {
      kind: 'attempt';
      chunkId: string;
      omissions: RankedResponsibilityOmission[];
      preOmissionCount: number;
    }
  | {
      kind: 'no_source_read';
      chunkId: string;
      omissions: RankedResponsibilityOmission[];
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
      omissions: selectFocusedResponsibilityOmissions(next.omissions).map((item) => ({
        ...item,
        rankFeatures: {
          ...item.rankFeatures,
          chunkOmissionCount: next.omissions.length,
          sourceChunkIndex: args.chunks.findIndex((chunk) => chunk.id === next.chunkId),
        },
      })),
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
    finalUncoveredSpanSample: args.finalOmissions.slice(0, 30).map((item) => ({
      chunkId: item.chunkId,
      spanIndex: item.spanIndex,
      sourceSpan: item.sourceSpan.slice(0, 2000),
      evidenceQuote: item.evidenceQuote?.slice(0, 2000) ?? null,
      evidenceQuoteSha256: item.evidenceQuote
        ? responsibilitySpanSha256(item.evidenceQuote)
        : null,
      sourceStart: item.sourceStart ?? null,
      sourceEnd: item.sourceEnd ?? null,
      sourceLocationFailure: item.sourceLocationFailure ?? null,
      sourceSpanSha256: responsibilitySpanSha256(item.sourceSpan.slice(0, 2000)),
    })),
    retries: [...args.retries],
  };
}

export function buildResponsibilityPostPassAudit<T extends {
  preOmissionCount: number;
  postOmissionCount: number;
}>(args: {
  initialOmissions: readonly ResponsibilityOmission[];
  finalOmissions: readonly ResponsibilityOmission[];
  retries: readonly T[];
  quoteRepair: unknown;
  postPassBudget: unknown;
  syntheticBaseReadCount: number;
}) {
  return {
    responsibilityOmissionAudit: buildResponsibilityOmissionAudit({
      initialOmissions: args.initialOmissions,
      finalOmissions: args.finalOmissions,
      retries: args.retries,
    }),
    responsibilityQuoteRepair: args.quoteRepair,
    responsibilityPostPassBudget: args.postPassBudget,
    syntheticBaseReadCount: args.syntheticBaseReadCount,
  };
}

export function selectResponsibilityQuoteRepairRead<T extends {
  segment: SourceStructureSegment;
  validation: {
    diagnostics: readonly ResponsibilityReaderDiagnostic[];
    incompleteInventoryAudit?: readonly ResponsibilityIncompleteAudit[];
  };
}>(reads: readonly T[]): T | undefined {
  return [...reads]
    .filter((read) =>
      read.validation.diagnostics.some((item) => item.failureClass === 'quote_mismatch') ||
      Boolean(read.validation.incompleteInventoryAudit?.length),
    )
    .sort(
      (a, b) =>
        b.validation.diagnostics.filter((item) => item.failureClass === 'quote_mismatch').length -
          a.validation.diagnostics.filter((item) => item.failureClass === 'quote_mismatch').length ||
        (b.validation.incompleteInventoryAudit?.length ?? 0) -
          (a.validation.incompleteInventoryAudit?.length ?? 0) ||
        a.segment.segmentId.localeCompare(b.segment.segmentId),
    )[0];
}

export function buildResponsibilitySelectedSpanAudit(args: {
  selected: readonly RankedResponsibilityOmission[];
  finalOmissions: readonly ResponsibilityOmission[];
  preRecordCount: number;
  postRecordCount: number;
  skipped: string | null;
  sourceShapes?: readonly string[];
  sourceSegmentIds?: readonly string[];
  inResponsibilityBaseRead: boolean;
  fieldAudits?: ReturnType<typeof canonicalizeForcedResponsibilityOutput>['audits'];
}) {
  const finalKeys = new Set(
    args.finalOmissions.map((item) => `${item.chunkId}:${item.spanIndex}`),
  );
  const fieldById = new Map(
    (args.fieldAudits ?? []).map((audit) => [audit.forcedResponsibilityId, audit]),
  );
  return args.selected.map((item) => {
    const forcedResponsibilityId =
      'forcedResponsibilityId' in item
        ? (item as ForcedResponsibilitySpan).forcedResponsibilityId
        : null;
    const fieldAudit = forcedResponsibilityId
      ? fieldById.get(forcedResponsibilityId) ?? null
      : null;
    return {
    chunkId: item.chunkId,
    spanIndex: item.spanIndex,
    sourceSpan: item.sourceSpan.slice(0, 2000),
    evidenceQuote: item.evidenceQuote?.slice(0, 2000) ?? null,
    evidenceQuoteSha256: item.evidenceQuote
      ? responsibilitySpanSha256(item.evidenceQuote)
      : null,
    sourceStart: item.sourceStart ?? null,
    sourceEnd: item.sourceEnd ?? null,
    sourceLocationFailure: item.sourceLocationFailure ?? null,
    sourceSpanSha256: responsibilitySpanSha256(item.sourceSpan.slice(0, 2000)),
    forcedResponsibilityId,
    rankFeatures: item.rankFeatures,
    rankIndex: item.rankIndex,
    preRecordCount: args.preRecordCount,
    postRecordCount: args.postRecordCount,
    result: fieldAudit
      ? {
          accepted: fieldAudit.accepted,
          skipped: fieldAudit.accepted ? null : 'field_or_validation_reject',
        }
      : args.skipped
      ? { accepted: false, skipped: args.skipped }
      : finalKeys.has(`${item.chunkId}:${item.spanIndex}`)
        ? { accepted: false, skipped: 'not_covered' }
        : { accepted: true, skipped: null },
    sourceShapes: [...(args.sourceShapes ?? [])],
    sourceSegmentIds: [...(args.sourceSegmentIds ?? [])],
    inResponsibilityBaseRead: args.inResponsibilityBaseRead,
    returnedRao: fieldAudit?.returnedRao ?? null,
    exactQuoteBinding: fieldAudit?.exactQuoteBinding ?? false,
    fieldFidelity: fieldAudit?.fieldFidelity ?? null,
    polarityFailure: fieldAudit?.fieldFidelity.polarityFailure ?? false,
    multiVerbReject: fieldAudit?.fieldFidelity.multiVerbReject ?? false,
    rejectionReasons: fieldAudit?.rejectionReasons ?? [],
  };
  });
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

function responsibilityElement(
  record: ResponsibilityReadOutput['responsibilities'][number],
  segmentId: string,
  evidenceQuote: string,
): SourceStructureElement {
  return {
    elementId: record.responsibilityId,
    segmentId,
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
    evidenceQuote,
    chunkId: record.chunkId,
  };
}

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
  inventoryElements: SourceStructureElement[];
  completeElementIds: string[];
  fieldDiagnostics: Record<string, ResponsibilityFieldFidelityResult>;
  incompleteInventoryAudit: ResponsibilityIncompleteAudit[];
  expansionAudit: ResponsibilityExpansionAudit[];
  diagnostics: ResponsibilityReaderDiagnostic[];
  crossSegmentCitations: Array<{ responsibilityId: string; chunkId: string }>;
  primaryCount: number;
} {
  const diagnostics: ResponsibilityReaderDiagnostic[] = [];
  const elements: SourceStructureElement[] = [];
  const inventoryElements: SourceStructureElement[] = [];
  const completeElementIds: string[] = [];
  const fieldDiagnostics: Record<string, ResponsibilityFieldFidelityResult> = {};
  const incompleteInventoryAudit: ResponsibilityIncompleteAudit[] = [];
  const expansionAudit: ResponsibilityExpansionAudit[] = [];
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
    const enclosingDutySpan = resolveEnclosingResponsibilityDutySpan({
      rawText: chunk.rawText,
      evidenceQuote: quote.validatedExactQuote ?? record.evidenceQuote,
      fileType: args.fileType,
      fileName: args.fileName,
    });
    const fieldFidelity = enclosingDutySpan
      ? validateResponsibilityFieldFidelity(enclosingDutySpan, record)
      : null;
    if (enclosingDutySpan) {
      const expansion = expandResponsibilityDestinations({
        sourceSpan: enclosingDutySpan,
        record,
      });
      expansionAudit.push(...expansion.audit);
      if (expansion.records.length > 0) {
        inventoryElements.push(
          responsibilityElement(
            record,
            args.segment.segmentId,
            quote.validatedExactQuote ?? record.evidenceQuote,
          ),
        );
        incompleteInventoryAudit.push({
          elementId: record.responsibilityId,
          chunkId: record.chunkId,
          failureCategory: 'field',
          repairStatus: 'repaired',
          decisionReason: 'replaced_by_deterministic_destination_expansion',
          quoteSha256: createHash('sha256')
            .update(quote.validatedExactQuote ?? record.evidenceQuote)
            .digest('hex'),
          selectedSourceSpan: enclosingDutySpan,
        });
        for (const expandedRecord of expansion.records) {
          const expandedElement = responsibilityElement(
            expandedRecord,
            args.segment.segmentId,
            quote.validatedExactQuote ?? record.evidenceQuote,
          );
          inventoryElements.push(expandedElement);
          const expandedFidelity = validateResponsibilityFieldFidelity(
            destinationSpecificResponsibilitySpan(
              enclosingDutySpan,
              expandedRecord.requiredSystem ?? '',
            ),
            expandedRecord,
          );
          if (expandedFidelity.passed) {
            elements.push(expandedElement);
            completeElementIds.push(expandedElement.elementId);
          } else {
            fieldDiagnostics[expandedRecord.responsibilityId] = expandedFidelity;
            incompleteInventoryAudit.push({
              elementId: expandedRecord.responsibilityId,
              chunkId: expandedRecord.chunkId,
              failureCategory: expandedFidelity.multiVerbReject ? 'multi_verb' : 'field',
              repairStatus: 'rejected',
              decisionReason: expandedFidelity.reasons.join('; '),
              quoteSha256: createHash('sha256')
                .update(expandedRecord.evidenceQuote)
                .digest('hex'),
              selectedSourceSpan: enclosingDutySpan,
            });
          }
        }
        continue;
      }
    }
    if (fieldFidelity && !fieldFidelity.passed) {
      const inventoryElement = responsibilityElement(
        record,
        args.segment.segmentId,
        quote.validatedExactQuote ?? record.evidenceQuote,
      );
      inventoryElements.push(inventoryElement);
      fieldDiagnostics[record.responsibilityId] = fieldFidelity;
      const failureCategory: ResponsibilityFailureCategory = fieldFidelity.multiVerbReject
        ? 'multi_verb'
        : 'field';
      incompleteInventoryAudit.push({
        elementId: record.responsibilityId,
        chunkId: record.chunkId,
        failureCategory,
        repairStatus: 'not_selected',
        decisionReason: fieldFidelity.reasons.join('; '),
        quoteSha256: createHash('sha256')
          .update(quote.validatedExactQuote ?? record.evidenceQuote)
          .digest('hex'),
        selectedSourceSpan: enclosingDutySpan ?? record.evidenceQuote,
      });
      diagnostics.push({
        ...base,
        failureClass: 'invalid_detail',
        detail: `Field fidelity failed: ${fieldFidelity.reasons.join('; ')}`,
        validationMethod: quote.validationMethod,
      });
      continue;
    }
    if (!covered.has(chunk.id)) {
      crossSegmentCitations.push({
        responsibilityId: record.responsibilityId,
        chunkId: record.chunkId,
      });
    }
    const acceptedElement = responsibilityElement(
      record,
      args.segment.segmentId,
      quote.validatedExactQuote ?? record.evidenceQuote,
    );
    inventoryElements.push(acceptedElement);
    elements.push(acceptedElement);
    completeElementIds.push(acceptedElement.elementId);
  }
  return {
    elements,
    inventoryElements,
    completeElementIds,
    fieldDiagnostics,
    incompleteInventoryAudit,
    expansionAudit,
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
