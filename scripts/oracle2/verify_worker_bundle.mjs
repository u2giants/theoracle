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
