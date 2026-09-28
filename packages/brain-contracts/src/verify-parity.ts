import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { candidateBundle, projectionReceipt, runRequest } from './index.js';

const fixtures = JSON.parse(readFileSync(fileURLToPath(new URL('../schema/parity-fixtures.json', import.meta.url)), 'utf8')) as
  { contract: 'candidateBundle' | 'projectionReceipt' | 'runRequest'; valid: boolean; value: unknown }[];
const contracts = { candidateBundle, projectionReceipt, runRequest };
for (const [index, fixture] of fixtures.entries()) {
  const actual = contracts[fixture.contract].safeParse(fixture.value).success;
  if (actual !== fixture.valid) {
    throw new Error(`Contract fixture ${index} disagrees with expected result`);
  }
}
console.log(`${fixtures.length} TypeScript contract fixtures passed`);
