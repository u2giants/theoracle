import { relative, sep } from 'node:path';

export const DEPRECATED_SQL_COLUMNS = [
  'auth_user_id',
  'auth_provider',
  'auth_provider_subject',
] as const;
export const AUTHORIZED_IDENTITY_DROP_MIGRATION =
  'packages/db/migrations/sql/98_drop_deprecated_employee_identity_columns.sql';
export const GAP10_ROLLBACK_PROOF = {
  commit: '53047981e2580bbba56451aaf4aeb034d9a92b3b',
  ciRun: '30424102001',
  deployment: 'dpl_7MVqENiyLL3FeQCiB9f4vmTiMCQq',
} as const;
export const GAP10_FINAL_RELEASE_PROOF = {
  commit: '30eed149ef89c2ab5f68390cde704daba63d2f69',
  ciRun: '30424618491',
  deployment: 'dpl_DeZNsq6RduGKZs2dQhw2RtmJMEHs',
} as const;

export function classifyLegacyIdentityColumnState(
  presentColumns: readonly string[],
): 'pre-drop' | 'post-drop' {
  const expected = new Set<string>(DEPRECATED_SQL_COLUMNS);
  const present = new Set(presentColumns);
  const unknown = [...present].filter((column) => !expected.has(column));
  if (unknown.length > 0) {
    throw new Error(`Unknown legacy identity columns reported: ${unknown.join(', ')}`);
  }
  if (present.size === 0) return 'post-drop';
  if (present.size === expected.size && [...expected].every((column) => present.has(column))) {
    return 'pre-drop';
  }
  throw new Error(
    `Partial legacy identity-column state: found ${[...present].sort().join(', ') || 'none'}; expected all three or none.`,
  );
}

export function shouldSkipRawMigration(
  fileName: string,
  legacyAuthUserIdColumnExists: boolean | undefined,
): boolean {
  if (fileName !== '40_employee_identities_data.sql') return false;
  if (legacyAuthUserIdColumnExists === undefined) {
    throw new Error('Legacy identity-column state is unknown; refusing to skip migration 40.');
  }
  return !legacyAuthUserIdColumnExists;
}

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
  if (normalized === AUTHORIZED_IDENTITY_DROP_MIGRATION) {
    const errors = validateAuthorizedIdentityDropMigration(sql);
    return errors.length === 0 ? null : `authorized GAP-10 migration is invalid: ${errors.join('; ')}`;
  }
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

export function validateAuthorizedIdentityDropMigration(sql: string): string[] {
  const errors: string[] = [];
  const dropped = new Set(findDeprecatedDropColumns(sql));
  for (const column of DEPRECATED_SQL_COLUMNS) {
    if (!dropped.has(column)) errors.push(`missing DROP COLUMN ${column}`);
    if (
      !new RegExp(`\\bdrop\\s+column\\s+if\\s+exists\\s+"?${column}"?\\b`, 'i').test(sql)
    ) {
      errors.push(`${column} drop is not rerun-safe`);
    }
  }
  if (dropped.size !== DEPRECATED_SQL_COLUMNS.length) {
    errors.push('migration drops unexpected deprecated columns');
  }
  const employeeDropColumns = new Set<string>();
  const withoutComments = sql.replace(/--.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const statement of withoutComments.split(';')) {
    if (
      !/\balter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:"?public"?\s*\.\s*)?"?employees"?\b/i.test(
        statement,
      )
    ) {
      continue;
    }
    for (const match of statement.matchAll(
      /\bdrop\s+column\s+(?:if\s+exists\s+)?["']?([A-Za-z_][\w$]*)["']?/gi,
    )) {
      if (match[1]) employeeDropColumns.add(match[1].toLowerCase());
    }
  }
  const extraColumns = [...employeeDropColumns].filter(
    (column) => !DEPRECATED_SQL_COLUMNS.includes(column as (typeof DEPRECATED_SQL_COLUMNS)[number]),
  );
  if (extraColumns.length > 0) {
    errors.push(`migration drops unrelated employees columns: ${extraColumns.join(', ')}`);
  }
  if (
    !/\balter\s+table\s+(?:only\s+)?public\.employees\s+drop\s+constraint\s+if\s+exists\s+employees_auth_user_id_unique\b/i.test(
      sql,
    )
  ) {
    errors.push('missing rerun-safe local unique constraint drop');
  }
  if (
    !/\bdrop\s+index\s+if\s+exists\s+public\.employees_auth_user_id_unique\b/i.test(sql)
  ) {
    errors.push('missing rerun-safe local unique index drop');
  }
  if (!/\bbegin\s*;/i.test(sql) || !/\bcommit\s*;/i.test(sql)) {
    errors.push('migration must be transactional');
  }
  if (/\b(drop\s+table|truncate|delete\s+from|update\s+|insert\s+into)\b/i.test(sql)) {
    errors.push('migration contains an unrelated destructive statement');
  }
  const constraintPosition = sql.search(/\bdrop\s+constraint\b/i);
  const indexPosition = sql.search(/\bdrop\s+index\b/i);
  const columnPosition = sql.search(/\bdrop\s+column\b/i);
  if (
    constraintPosition < 0 ||
    indexPosition < constraintPosition ||
    columnPosition < indexPosition
  ) {
    errors.push('constraint, index, and columns must be dropped in that order');
  }
  return errors;
}
