/**
 * Settings value encoding — single source of truth for keeping the `settings`
 * jsonb column single-encoded (Bug 4).
 *
 * `settings.value` is a Postgres `jsonb` column. Drizzle JSON-encodes whatever
 * JS value the writer passes, so:
 *   - writing the bare string `"off"`        → stored jsonb `"off"`        (correct)
 *   - writing the bare array `["a","b"]`      → stored jsonb `["a","b"]`    (correct)
 *   - writing the STRING `'"off"'` (already   → stored jsonb `"\"off\""`   (DOUBLE-ENCODED)
 *     JSON-encoded) by mistake
 *   - writing the STRING `'["a","b"]'`        → stored jsonb as a string    (DOUBLE-ENCODED)
 *
 * The consumers (`resolveRouteCandidates`, the admin picker loader) expect the
 * decoded value and silently break on the double-encoded form (an effort string
 * with literal quotes fails `isReasoningEffort`; a pool that is a string instead
 * of an array reads as an empty pool).
 *
 * `normalizeSettingValue` makes every write idempotent and self-healing: it
 * unwraps an accidental encode layer while leaving a correctly-typed value
 * untouched. The only legitimate scalar string settings (model ids like
 * `google/gemini-2.5-flash`, efforts like `off`, `sync`/`batch`) are never
 * themselves valid JSON documents — they have no surrounding quotes/brackets —
 * so they are never unwrapped.
 */
export function normalizeSettingValue(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  const looksEncoded =
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    trimmed.startsWith('[') ||
    trimmed.startsWith('{');
  if (!looksEncoded) return value;
  try {
    const decoded: unknown = JSON.parse(value);
    // Recurse so a (pathological) triple-encode also collapses; stop as soon as
    // the value is no longer an encoded-string wrapper.
    return normalizeSettingValue(decoded);
  } catch {
    return value;
  }
}

/**
 * True when a value already stored in (or about to be written to) the jsonb
 * column is double-encoded — i.e. a string that is itself a JSON document. Used
 * by the regression guard and by read-time health checks.
 */
export function isDoubleEncodedSettingValue(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  const trimmed = value.trim();
  const looksEncoded =
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    trimmed.startsWith('[') ||
    trimmed.startsWith('{');
  if (!looksEncoded) return false;
  try {
    JSON.parse(value);
    return true;
  } catch {
    return false;
  }
}
