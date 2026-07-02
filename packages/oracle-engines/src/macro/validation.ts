const ENTITY_STOPWORDS = new Set([
  'Admin',
  'Approved',
  'Brain',
  'Claim',
  'Claims',
  'Company',
  'Document',
  'Exception',
  'If',
  'Macro',
  'Oracle',
  'Policy',
  'Process',
  'Relationship',
  'Review',
  'SOP',
  'Source',
  'Step',
  'The',
  'This',
  'When',
]);

export type MacroEntityValidationResult = {
  ok: boolean;
  unsupportedEntities: string[];
};

function normalizeEntity(value: string): string {
  return value.toLowerCase().replace(/['’]s\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function containsNormalizedPhrase(haystack: string, needle: string): boolean {
  if (!needle) return false;
  return new RegExp(`(^|[^a-z0-9])${escapeRegExp(needle)}($|[^a-z0-9])`, 'i').test(haystack);
}

export function extractLikelyNamedEntities(text: string): string[] {
  return extractLikelyNamedEntitiesWithStopwords(text);
}

function extractLikelyNamedEntitiesWithStopwords(text: string, extraStopwords: string[] = []): string[] {
  const stopwords = new Set([
    ...ENTITY_STOPWORDS,
    ...extraStopwords.map((word) => word.trim()).filter(Boolean),
  ]);
  const matches = text.match(/\b(?:[A-Z][A-Za-z0-9&.'’/-]*(?:\s+|$)){1,5}/g) ?? [];
  const entities = matches
    .map((match) => match.trim().replace(/[.,;:!?]+$/g, ''))
    .filter((match) => match.length >= 3)
    .filter((match) => !stopwords.has(match))
    .filter((match) => !/^(ID|IDs|JSON|URL|API|DB)$/i.test(match));
  return Array.from(new Set(entities));
}

export function validateMacroRelationshipSummaryEntities(args: {
  summary: string;
  supportClaimSummaries: string[];
  registryEntityNames?: string[];
  extraStopwords?: string[];
}): MacroEntityValidationResult {
  const supportText = normalizeEntity(args.supportClaimSummaries.join('\n'));
  const registry = new Set((args.registryEntityNames ?? []).map(normalizeEntity).filter(Boolean));
  const unsupportedEntities = extractLikelyNamedEntitiesWithStopwords(
    args.summary,
    args.extraStopwords,
  ).filter((entity) => {
    const normalized = normalizeEntity(entity);
    if (!normalized) return false;
    if (containsNormalizedPhrase(supportText, normalized)) return false;
    return !registry.has(normalized);
  });

  return {
    ok: unsupportedEntities.length === 0,
    unsupportedEntities,
  };
}
