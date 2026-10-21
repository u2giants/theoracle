export type TargetKey = 'legacy_trigger_project' | 'native_trigger_project' | 'oracle_supabase_project' | 'native_supabase_project' | 'coolify_api_base_url';
export function defaultTargetProfile(): string;
export function targetPins(): Readonly<Record<TargetKey, string>>;
export function isPinnedTarget(key: TargetKey, value: unknown): value is string;
export function assertPinnedTarget(key: TargetKey, value: unknown): string;
export function validateTargetDocument(value: unknown, pins?: Record<string, string>): Readonly<Record<string, string>>;
export function readBoundedTargetJson(path: string, options?: {privateProfile?: boolean}): unknown;
export function readPrivateTarget(key: TargetKey, profilePath?: string): string;
export function resolveNativeTriggerProject(env?: Record<string, string | undefined>, options?: {allowDefault?: boolean}): string;
