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

if (pkg.scripts?.['build:vercel'] !== 'pnpm --filter @oracle/web build') {
  throw new Error('build:vercel must build the web app.');
}

console.log(
  `PASS: Vercel buildCommand is ${command.length}/256 characters and delegates to build:vercel.`,
);
