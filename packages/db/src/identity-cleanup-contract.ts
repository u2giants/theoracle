import { relative, sep } from 'node:path';

export const DEPRECATED_SQL_COLUMNS = [
  'auth_user_id',
  'auth_provider',
  'auth_provider_subject',
] as const;

const DEPRECATED_TS_PROPERTIES = 'authUserId|authProvider|authProviderSubject';
const DEPRECATED_SQL_PATTERN = 'auth_user_id|auth_provider|auth_provider_subject';

export function normalizeRepoPath(path: string): string {
  return path.replaceAll('\\', '/').replace(/^\.\/+/, '');
}

export function repoRelative(repoRoot: string, path: string): string {
  return normalizeRepoPath(relative(repoRoot, path).split(sep).join('/'));
}

export function isIgnoredOwnedPath(path: string): boolean {
  const normalized = normalizeRepoPath(path);
  return (
    normalized === 'packages/db/src/verify-identities.ts' ||
    normalized === 'packages/db/src/identity-cleanup-contract.ts' ||
    normalized === 'packages/db/src/verify-identity-cleanup-contract.ts' ||
    normalized.startsWith('packages/db/migrations/') ||
    normalized.split('/').some((part) => ['node_modules', '.next', 'dist'].includes(part))
  );
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
    .replace(/--.*$/gm, '');
}

export function hasDeprecatedEmployeeReader(path: string, source: string): boolean {
  if (isIgnoredOwnedPath(path)) return false;
  const code = stripComments(source);

  // Resolve every local name bound to the employees schema export. This catches
  // direct imports, renamed imports, and namespace imports.
  const bindings = new Set<string>();
  for (const match of code.matchAll(/\bimport\s*\{([^}]*)\}\s*from\s*['"][^'"]+['"]/g)) {
    for (const specifier of match[1]?.split(',') ?? []) {
      const binding = specifier
        .trim()
        .match(/^employees(?:\s+as\s+([A-Za-z_$][\w$]*))?$/)?.[1];
      if (binding) bindings.add(binding);
      else if (specifier.trim() === 'employees') bindings.add('employees');
    }
  }
  for (const match of code.matchAll(
    /\bimport\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from\s*['"][^'"]+['"]/g,
  )) {
    const namespace = match[1];
    if (namespace) bindings.add(`${namespace}.employees`);
  }
  for (const binding of bindings) {
    const escaped = binding.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (new RegExp(`\\b${escaped}\\s*(?:\\.|\\?\\.)\\s*(?:${DEPRECATED_TS_PROPERTIES})\\b`).test(code)) {
      return true;
    }
    if (
      new RegExp(
        `\\b${escaped}\\s*\\[\\s*['"](?:${DEPRECATED_TS_PROPERTIES})['"]\\s*\\]`,
      ).test(code)
    ) {
      return true;
    }
  }

  // SQL can put SELECT before FROM, use any alias, omit the alias, or write.
  // Bind aliases to relations so `ei.auth_user_id` remains valid when `ei`
  // names employee_identities in a join.
  const sqlStatements = code.split(';');
  return sqlStatements.some((statement) => {
    const employeeAliases = new Set<string>(['employees']);
    let hasEmployees = false;
    for (const match of statement.matchAll(
      /\b(?:from|join|update|into|table)\s+(?:"?public"?\s*\.\s*)?"?employees"?(?:\s+(?:as\s+)?([A-Za-z_][\w$]*))?/gi,
    )) {
      hasEmployees = true;
      if (match[1] && !['set', 'where', 'join', 'on', 'returning'].includes(match[1].toLowerCase())) {
        employeeAliases.add(match[1]);
      }
    }
    if (!hasEmployees) return false;

    for (const alias of employeeAliases) {
      if (
        new RegExp(
          `\\b${alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\.\\s*(?:${DEPRECATED_SQL_PATTERN})\\b`,
          'i',
        ).test(statement)
      ) {
        return true;
      }
    }

    const withoutQualifiedColumns = statement.replace(
      new RegExp(
        `\\b[A-Za-z_][\\w$]*\\s*\\.\\s*(?:${DEPRECATED_SQL_PATTERN})\\b`,
        'gi',
      ),
      '',
    );
    const unqualifiedDeprecated = new RegExp(
      `(^|[^.\\w])(?:${DEPRECATED_SQL_PATTERN})\\b`,
      'i',
    ).test(withoutQualifiedColumns);
    return unqualifiedDeprecated;
  });
}

export function findDeprecatedDropColumns(sql: string): string[] {
  const withoutComments = sql
    .replace(/--.*$/gm, '')
    .replace(/\/\*[\s\S]*?\*\//g, '');
  const found = new Set<string>();
  for (const statement of withoutComments.split(';')) {
    if (!/\balter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:"?public"?\s*\.\s*)?"?employees"?\b/i.test(statement)) {
      continue;
    }
    for (const column of DEPRECATED_SQL_COLUMNS) {
      if (
        new RegExp(
          `\\bdrop\\s+column\\s+(?:if\\s+exists\\s+)?["']?${column}["']?\\b`,
          'i',
        ).test(statement)
      ) {
        found.add(column);
      }
    }
  }
  return [...found];
}

export function describeBlockedDropMigration(
  path: string,
  sql: string,
  rawMigrationNames: string[],
): string | null {
  const columns = findDeprecatedDropColumns(sql);
  if (columns.length === 0) return null;
  const normalized = normalizeRepoPath(path);
  const name = normalized.split('/').at(-1) ?? normalized;
  if (/^packages\/db\/migrations\/[^/]+\.sql$/.test(normalized)) {
    return `generated ${name} drops ${columns.join(', ')} before raw migration 40 can run`;
  }
  const sorted = [...rawMigrationNames].sort();
  const backfillIndex = sorted.indexOf('40_employee_identities_data.sql');
  if (backfillIndex < 0 || sorted.indexOf(name) <= backfillIndex) {
    return `${name} drops ${columns.join(', ')} before migration 40`;
  }
  return `${name} drops ${columns.join(', ')} before the live GAP-10 proof is recorded`;
}
