export type ModelCoverageSource = {
  sourceType: string;
  sourceId: string;
  mapId: string;
  mapElementRef: string;
  mapElementKind: string;
  mapShape: string;
  mapElementLocalId: string;
};

export const MODEL_COVERAGE_PAGE_SIZE = 25;

export function parseModelCoveragePage(value: string | undefined): number {
  if (!value || !/^\d+$/.test(value)) return 1;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1;
}

export function clampModelCoveragePage(page: number, totalRows: number): number {
  const totalPages = Math.max(1, Math.ceil(totalRows / MODEL_COVERAGE_PAGE_SIZE));
  return Math.min(Math.max(1, page), totalPages);
}

export function requireModelCoverageSource(value: unknown): ModelCoverageSource {
  if (!value || typeof value !== 'object') {
    throw new Error('This finding has no stable source details and cannot be converted.');
  }
  const row = value as Record<string, unknown>;
  const keys = [
    'sourceType',
    'sourceId',
    'mapId',
    'mapElementRef',
    'mapElementKind',
    'mapShape',
    'mapElementLocalId',
  ] as const;
  for (const key of keys) {
    if (typeof row[key] !== 'string' || !row[key].trim()) {
      throw new Error(`This finding is missing ${key} and cannot be converted.`);
    }
  }
  return Object.fromEntries(keys.map((key) => [key, row[key]])) as ModelCoverageSource;
}

export function assertCoverageFindingEligible(row: {
  gapType: string;
  status: string;
  sourceContext: unknown;
}) {
  if (row.gapType !== 'model_coverage') throw new Error('Only model coverage findings can be converted.');
  if (row.status !== 'open') throw new Error('Only an open model coverage finding can be converted.');
  return requireModelCoverageSource(row.sourceContext);
}

export function modelCoverageSourcesEqual(left: unknown, right: unknown): boolean {
  const normalizedLeft = requireModelCoverageSource(left);
  const normalizedRight = requireModelCoverageSource(right);
  return (
    normalizedLeft.sourceType === normalizedRight.sourceType &&
    normalizedLeft.sourceId === normalizedRight.sourceId &&
    normalizedLeft.mapId === normalizedRight.mapId &&
    normalizedLeft.mapElementRef === normalizedRight.mapElementRef &&
    normalizedLeft.mapElementKind === normalizedRight.mapElementKind &&
    normalizedLeft.mapShape === normalizedRight.mapShape &&
    normalizedLeft.mapElementLocalId === normalizedRight.mapElementLocalId
  );
}
