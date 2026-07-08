import { eq, inArray } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';
import { modelCapabilities, settings } from '@oracle/db/schema';
import { getAuxiliaryModelDef } from './auxiliary';
import {
  ENFORCE_MODEL_CAPABILITIES_SETTING_KEY,
  MODEL_POOL_SETTING_KEYS,
  REASONING_EFFORT_SETTING_KEYS,
  ROUTE_SETTING_KEYS,
} from './defaults';
import { ModelCapabilityError, NoConfiguredModelError, type ModelSlot } from './errors';
import { missingRequirements } from './capability-requirements';
import { providerModelIdForRoute, resolveModelRoute, type SyntheticRouteCaps } from './resolve';
import { normalizeDirectProviderCapabilities, type ModelCapability } from '../model-capabilities';
import type { OracleModelRole, OracleModelRoute, ReasoningEffort } from './types';

export interface RouteCandidate {
  route: OracleModelRoute;
  slot: ModelSlot;
  isPrimary: boolean;
  approvedModelId: string;
}

export interface SkippedRouteCandidate {
  slot: ModelSlot;
  modelIdOrRouteId: string;
  reason: string;
}

export interface RouteCandidateResolution {
  slot: ModelSlot;
  candidates: RouteCandidate[];
  skipped: SkippedRouteCandidate[];
}

function isReasoningEffort(v: unknown): v is ReasoningEffort {
  return v === 'off' || v === 'low' || v === 'medium' || v === 'high';
}

function isPipelineSlot(slot: ModelSlot): slot is OracleModelRole {
  return slot === 'interview' || slot === 'extraction' || slot === 'synthesis';
}

function roleForSlot(slot: ModelSlot): OracleModelRole {
  if (slot === 'workflow_read' || slot === 'macro') return 'synthesis';
  if (slot === 'model_merge') return 'extraction';
  if (slot === 'transcript_summary') return 'extraction';
  return isPipelineSlot(slot) ? slot : 'extraction';
}

function settingKeysForSlot(slot: ModelSlot): {
  routeKey: string;
  effortKey?: string;
  poolKey?: string;
} {
  if (isPipelineSlot(slot)) {
    return {
      routeKey: ROUTE_SETTING_KEYS[slot],
      effortKey: REASONING_EFFORT_SETTING_KEYS[slot],
      poolKey: MODEL_POOL_SETTING_KEYS[slot],
    };
  }
  const def = getAuxiliaryModelDef(slot);
  if (!def) throw new NoConfiguredModelError(slot, 'unknown auxiliary model id');
  return {
    routeKey: def.routeSettingKey,
    effortKey: def.reasoningEffortSettingKey,
    poolKey: def.poolSettingKey,
  };
}

function capToRouteCaps(cap: ModelCapability): SyntheticRouteCaps {
  const normalized = normalizeProviderCapabilities(cap);
  return {
    supportsVision: normalized.vision,
    supportsToolCalling: normalized.toolCalling,
    supportsStructuredOutput: normalized.structuredOutputs,
    supportsReasoningControls: normalized.thinking,
    enabled: true,
  };
}

function isQwenVisionModel(id: string): boolean {
  const lower = id.toLowerCase();
  return lower.includes('-vl') || lower.includes('/vl-') || lower.includes('omni');
}

/**
 * Runtime guards must be stricter than third-party catalog enrichment. Qwen's
 * text-only models can be over-tagged at the family level; only VL/omni models
 * should satisfy the image-vision slot.
 */
function normalizeProviderCapabilities(cap: ModelCapability): ModelCapability {
  const directNormalized = normalizeDirectProviderCapabilities(cap);
  if (cap.provider === 'qwen' && cap.vision && !isQwenVisionModel(cap.id)) {
    return { ...directNormalized, vision: false };
  }
  return directNormalized;
}

function catalogIdsForRoute(route: OracleModelRoute): string[] {
  const ids = [providerModelIdForRoute(route)];
  if (route.provider === 'vertex') ids.push(`google/${route.modelId}`);
  return ids;
}

async function readSettings(db: OracleDb, keys: string[]): Promise<Map<string, unknown>> {
  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(inArray(settings.key, keys));
  return new Map(rows.map((r) => [r.key, r.value]));
}

async function loadCapabilityMap(db: OracleDb, ids: string[]): Promise<Map<string, ModelCapability>> {
  if (ids.length === 0) return new Map();
  const unique = Array.from(new Set(ids));
  const rows = await db
    .select()
    .from(modelCapabilities)
    .where(inArray(modelCapabilities.id, unique));
  return new Map(
    rows.map((r) => [
      r.id,
      {
        id: r.id,
        provider: r.provider as ModelCapability['provider'],
        displayName: r.displayName,
        contextLength: r.contextLength,
        maxOutputTokens: r.maxOutputTokens,
        promptPer1mUsd: r.promptPer1mUsd != null ? Number(r.promptPer1mUsd) : null,
        completionPer1mUsd: r.completionPer1mUsd != null ? Number(r.completionPer1mUsd) : null,
        vision: r.vision,
        pdf: r.pdf,
        thinking: r.thinking,
        structuredOutputs: r.structuredOutputs,
        strictJsonSchema: r.strictJsonSchema,
        deepSchemaAccepted: r.deepSchemaAccepted,
        adapterParamsSafe: r.adapterParamsSafe,
        toolCalling: r.toolCalling,
        promptCaching: r.promptCaching,
        outputCap: r.outputCap,
        adapterParamNotes: r.adapterParamNotes ?? {},
        knowledgeCutoff: r.knowledgeCutoff,
        source: r.source as ModelCapability['source'],
      } satisfies ModelCapability,
    ]),
  );
}

async function enforceCapabilitiesEnabled(db: OracleDb): Promise<boolean> {
  const rows = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, ENFORCE_MODEL_CAPABILITIES_SETTING_KEY))
    .limit(1);
  return rows[0]?.value !== false;
}

function capabilityForRoute(
  route: OracleModelRoute,
  capabilityMap: Map<string, ModelCapability>,
): { id: string; cap: ModelCapability } | null {
  for (const id of catalogIdsForRoute(route)) {
    const cap = capabilityMap.get(id);
    if (cap) return { id, cap };
  }
  return null;
}

function resolveWithKnownCaps(
  modelIdOrRouteId: string,
  role: OracleModelRole,
  effort: ReasoningEffort | undefined,
  capMap: Map<string, ModelCapability>,
): OracleModelRoute | null {
  const directCap = capMap.get(modelIdOrRouteId);
  return resolveModelRoute(
    modelIdOrRouteId,
    role,
    effort,
    directCap ? capToRouteCaps(directCap) : undefined,
  );
}

export async function resolveRouteCandidates(
  db: OracleDb,
  slot: ModelSlot,
): Promise<RouteCandidateResolution> {
  const { routeKey, effortKey, poolKey } = settingKeysForSlot(slot);
  const keys = [
    routeKey,
    ...(effortKey ? [effortKey] : []),
    ...(poolKey ? [poolKey] : []),
    ENFORCE_MODEL_CAPABILITIES_SETTING_KEY,
  ];
  const rows = await readSettings(db, keys);

  const primaryValue = rows.get(routeKey);
  const primary = typeof primaryValue === 'string' ? primaryValue : null;
  if (!primary) throw new NoConfiguredModelError(slot, `${routeKey} is unset`);

  const effort = effortKey && isReasoningEffort(rows.get(effortKey))
    ? (rows.get(effortKey) as ReasoningEffort)
    : undefined;
  const role = roleForSlot(slot);
  const enforceCaps = await enforceCapabilitiesEnabled(db);

  const pool = poolKey && Array.isArray(rows.get(poolKey))
    ? (rows.get(poolKey) as unknown[]).filter((v): v is string => typeof v === 'string')
    : [];

  if (poolKey && pool.length === 0) {
    throw new NoConfiguredModelError(slot, `${poolKey} is empty`);
  }

  const probeIds = Array.from(new Set([primary, ...pool]));
  const capabilityMap = await loadCapabilityMap(db, probeIds);
  const primaryRoute = resolveWithKnownCaps(primary, role, effort, capabilityMap);
  if (!primaryRoute) throw new NoConfiguredModelError(slot, `${primary} cannot be resolved`);
  const primaryRouteCaps = await loadCapabilityMap(db, catalogIdsForRoute(primaryRoute));
  for (const [id, cap] of primaryRouteCaps) {
    capabilityMap.set(id, cap);
  }

  const primaryCatalogIds = catalogIdsForRoute(primaryRoute);
  const primaryApprovedId =
    poolKey
      ? pool.find((id) => id === primary || primaryCatalogIds.includes(id))
      : primaryCatalogIds.find((id) => capabilityMap.has(id)) ?? primary;

  if (poolKey && !primaryApprovedId) {
    throw new NoConfiguredModelError(
      slot,
      `${primary} resolves to ${primaryCatalogIds.join(' / ')} but is not in ${poolKey}`,
    );
  }

  const ordered = poolKey
    ? [primaryApprovedId!, ...pool.filter((id) => id !== primaryApprovedId)]
    : [primary];

  const candidates: RouteCandidate[] = [];
  const skipped: SkippedRouteCandidate[] = [];
  const seenConcrete = new Set<string>();

  for (const [index, id] of ordered.entries()) {
    const route = index === 0
      ? primaryRoute
      : resolveWithKnownCaps(id, role, effort, capabilityMap);
    if (!route) {
      skipped.push({ slot, modelIdOrRouteId: id, reason: 'unresolvable model id' });
      continue;
    }

    const concrete = providerModelIdForRoute(route);
    if (seenConcrete.has(concrete)) continue;
    seenConcrete.add(concrete);

    const capMatch = capabilityForRoute(route, capabilityMap);
    if (enforceCaps) {
      if (!capMatch) {
        const err = new ModelCapabilityError(slot, concrete, ['catalog metadata']);
        if (index === 0) throw err;
        skipped.push({ slot, modelIdOrRouteId: id, reason: err.message });
        continue;
      }
      const missing = missingRequirements(normalizeProviderCapabilities(capMatch.cap), slot);
      if (missing.length > 0) {
        const err = new ModelCapabilityError(slot, capMatch.id, missing);
        if (index === 0) throw err;
        skipped.push({ slot, modelIdOrRouteId: id, reason: err.message });
        continue;
      }
    }

    candidates.push({
      route,
      slot,
      isPrimary: index === 0,
      approvedModelId: poolKey ? id : capMatch?.id ?? concrete,
    });
  }

  if (candidates.length === 0) {
    throw new NoConfiguredModelError(slot, 'all configured candidates were invalid');
  }

  return { slot, candidates, skipped };
}

export async function resolvePrimaryRouteFromSettings(
  db: OracleDb,
  slot: ModelSlot,
): Promise<OracleModelRoute> {
  return (await resolveRouteCandidates(db, slot)).candidates[0]!.route;
}
