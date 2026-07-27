import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(import.meta.dirname, '..', '..');
const actions = readFileSync(join(root, 'app', 'admin', 'claims', '_actions.ts'), 'utf8');
const page = readFileSync(join(root, 'app', 'admin', 'claims', 'page.tsx'), 'utf8');
const worker = readFileSync(
  join(root, '..', 'workers', 'src', 'trigger', 'claim-translation.ts'),
  'utf8',
);

function requireText(source: string, text: string, message: string) {
  if (!source.includes(text)) throw new Error(message);
}

function functionBody(source: string, functionName: string): string {
  const signature = `export async function ${functionName}`;
  const start = source.indexOf(signature);
  if (start < 0) throw new Error(`${functionName} is missing`);
  const open = source.indexOf('{', start);
  let depth = 0;
  for (let index = open; index < source.length; index++) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(open, index + 1);
    }
  }
  throw new Error(`${functionName} has unbalanced braces`);
}

requireText(actions, 'export async function reviewClaimTranslation', 'review action is missing');
requireText(actions, 'export async function retranslateClaim', 'retranslate action is missing');
for (const functionName of [
  'reviewClaimTranslation',
  'retranslateClaim',
  'translateClaimsForChina',
]) {
  requireText(
    functionBody(actions, functionName),
    'await requireAdmin()',
    `${functionName} must require an admin inside its own function`,
  );
}
requireText(actions, "action: 'retranslation_requested'", 'retranslation request is not audited');
requireText(actions, "action: 'retranslation_dispatch_failed'", 'failed dispatch is not audited');
requireText(actions, 'expectedTranslationHash', 'review action lacks a translation content token');
requireText(actions, 'expectedUpdatedAt', 'review action lacks an updated-at token');
requireText(actions, 'eq(claimTranslations.updatedAt, expectedUpdatedAt)', 'review update is not concurrency guarded');
requireText(actions, 'eq(claimTranslations.summary, translation.summary)', 'review update is not content guarded');
requireText(page, 'Approve translation', 'approve control is missing');
requireText(page, 'Reject translation', 'reject control is missing');
requireText(page, 'translationIsStale', 'stale translation state is missing');
requireText(page, 'promptVersion', 'translation version is not displayed');
requireText(page, 'name="translationHash"', 'review form lacks a translation content token');
requireText(page, 'name="updatedAt"', 'review form lacks an updated-at token');
requireText(worker, "action: existing ? 'retranslated' : 'generated'", 'generation history is missing');
requireText(worker, "reviewStatus: 'pending_review'", 'new output must await review');
requireText(worker, 'beforeState: existing ?? null', 'prior output is not preserved');

console.log('PASS: translation review authorization, history, stale state, and controls are present.');
