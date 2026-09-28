// Proves each Oracle 2 task's runScript path is inside its config's scripts glob
// and resolves to a real file after sync_worker_python.sh.
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('../..', import.meta.url).pathname;
const workers = join(root, 'apps/workers');
execFileSync('sh', [join(root, 'scripts/oracle2/sync_worker_python.sh')], { stdio: 'inherit' });

const pairs = [
  ['trigger.oracle2-extract.config.ts', 'src/trigger/oracle2-run.ts'],
  ['trigger.oracle2-project.config.ts', 'src/trigger/oracle2-project.ts'],
];
for (const [config, task] of pairs) {
  const glob = readFileSync(join(workers, config), 'utf8').match(/scripts: \['([^']+)'\]/)?.[1];
  const script = readFileSync(join(workers, task), 'utf8').match(/_SCRIPT = '([^']+)'/)?.[1];
  if (!glob || !script) throw new Error(`${config}: scripts glob or script path missing`);
  const base = glob.replace(/\*\*\/\*\.py$/, '');
  if (!script.startsWith(base)) throw new Error(`${task}: ${script} is outside ${glob}`);
  if (!existsSync(join(workers, script))) throw new Error(`${task}: ${script} not found after sync`);
  console.log(`ok ${task} -> ${script}`);
}

// Identity guards must match dev/oracle2/runtime-identities.yaml forbidden lists.
const forbidden = {
  'src/trigger/oracle2-run.ts': ['ORACLE2_CONFIRMED_GRAPH_URL', 'ORACLE2_PROJECTION_SIGNING_KEY',
    'ORACLE2_CHECKPOINT_DATABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'],
  'src/trigger/oracle2-project.ts': ['ORACLE2_CANDIDATE_GRAPH_URL',
    'ORACLE2_CHECKPOINT_DATABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'],
};
for (const [task, names] of Object.entries(forbidden)) {
  const guard = readFileSync(join(workers, task), 'utf8').split('forbidden credentials')[0];
  for (const name of names) {
    if (!guard.includes(`process.env.${name}`)) throw new Error(`${task}: guard misses ${name}`);
  }
}
const legacy = readFileSync(join(workers, 'trigger.config.ts'), 'utf8');
if (!legacy.includes("'**/oracle2-run.ts'") || !legacy.includes("'**/oracle2-project.ts'")) {
  throw new Error('legacy trigger.config.ts must exclude Oracle 2 tasks');
}
console.log('ok identity guards and legacy exclusion');
