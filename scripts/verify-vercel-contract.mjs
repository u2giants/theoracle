import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const vercel = JSON.parse(readFileSync(resolve(root, 'vercel.json'), 'utf8'));
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));

const command = vercel.buildCommand;
if (typeof command !== 'string' || command.length === 0) {
  throw new Error('vercel.json buildCommand must be a non-empty string.');
}
if (command.length > 256) {
  throw new Error(`Vercel buildCommand is ${command.length} characters; maximum is 256.`);
}
if (command !== 'pnpm run build:vercel') {
  throw new Error('Vercel must call the stable root build:vercel script.');
}

const expectedGuards = [
  'pnpm --filter @oracle/ai verify:retrieval-filter-parity',
  'pnpm --filter @oracle/ai verify:chinese-retrieval',
  'pnpm --filter @oracle/ai verify:vertex-file-cache',
  'pnpm --filter @oracle/web verify:chat-attachment-safety',
  'pnpm --filter @oracle/web verify:claim-translation-review',
  'pnpm --filter @oracle/web verify:eval-results-dashboard',
  'pnpm --filter @oracle/web verify:provider-capability-parity',
  'pnpm --filter @oracle/web verify:model-coverage-conversion',
  'pnpm --filter @oracle/engines verify:lull-topical',
  'pnpm --filter @oracle/web verify:mcp',
];
const guardScript = pkg.scripts?.['verify:vercel-guards'];
if (guardScript !== expectedGuards.join(' && ')) {
  throw new Error('verify:vercel-guards does not contain the exact required guard list.');
}
if (guardScript.includes('verify:chinese-retrieval-live')) {
  throw new Error('Credentialed Chinese vector measurement must not run in Vercel.');
}
if (
  pkg.scripts?.['build:vercel'] !==
  'pnpm run verify:vercel-guards && pnpm --filter @oracle/web build'
) {
  throw new Error('build:vercel must run every guard before the production web build.');
}

console.log(
  `PASS: Vercel buildCommand is ${command.length}/256 characters and delegates to all ten network-free guards.`,
);
