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

export function extractLikelyNamedEntities(text: string): string[] {
  const matches = text.match(/\b(?:[A-Z][A-Za-z0-9&.'’/-]*(?:\s+|$)){1,5}/g) ?? [];
  const entities = matches
    .map((match) => match.trim().replace(/[.,;:!?]+$/g, ''))
    .filter((match) => match.length >= 3)
    .filter((match) => !ENTITY_STOPWORDS.has(match))
    .filter((match) => !/^(ID|IDs|JSON|URL|API|DB)$/i.test(match));
  return Array.from(new Set(entities));
}

export function validateMacroRelationshipSummaryEntities(args: {
  summary: string;
  supportClaimSummaries: string[];
  registryEntityNames?: string[];
}): MacroEntityValidationResult {
  const supportText = args.supportClaimSummaries.join('\n').toLowerCase();
  const registry = new Set((args.registryEntityNames ?? []).map(normalizeEntity).filter(Boolean));
  const unsupportedEntities = extractLikelyNamedEntities(args.summary).filter((entity) => {
    const normalized = normalizeEntity(entity);
    if (!normalized) return false;
    if (supportText.includes(normalized)) return false;
    return !registry.has(normalized);
  });

  return {
    ok: unsupportedEntities.length === 0,
    unsupportedEntities,
  };
}
