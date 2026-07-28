import { readFile, readdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const rawSqlDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'migrations', 'sql');
const files = (await readdir(rawSqlDir)).filter((file) => file.endsWith('.sql')).sort();
const constraintName = 'extraction_validation_results_check_name_check';
const definitions: Array<{ file: string; values: Set<string> }> = [];

for (const file of files) {
  const source = await readFile(resolve(rawSqlDir, file), 'utf8');
  const constraintStart = source.indexOf(`ADD CONSTRAINT ${constraintName}`);
  if (constraintStart < 0) continue;
  const tail = source.slice(constraintStart);
  const match = tail.match(/CHECK\s*\(\s*check_name\s+IN\s*\(([\s\S]*?)\)\s*\)/i);
  if (!match) throw new Error(`${file} has an unreadable ${constraintName} definition.`);
  const values = new Set(
    [...match[1]!.matchAll(/'([^']+)'/g)].map((item) => item[1]!),
  );
  definitions.push({ file, values });
}

if (definitions.length < 2) {
  throw new Error(`Expected the raw migration chain to define ${constraintName} more than once.`);
}

const currentValues = new Set(definitions.flatMap((definition) => [...definition.values]));
for (const definition of definitions) {
  const missing = [...currentValues].filter((value) => !definition.values.has(value));
  if (missing.length > 0) {
    throw new Error(
      `${definition.file} would reject current populated rows during a full rerun: ${missing.join(', ')}`,
    );
  }
}

console.log(
  `PASS raw constraint chain accepts all ${currentValues.size} current validation check names at every redefinition`,
);
