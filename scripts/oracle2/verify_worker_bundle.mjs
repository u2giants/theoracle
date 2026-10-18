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
  ['trigger.oracle2-holistic.config.ts', 'src/trigger/oracle2-holistic.ts'],
  ['trigger.oracle2-operating.config.ts', 'src/trigger/oracle2-operating-model.ts'],
  ['trigger.oracle2-native-invented.config.ts', 'src/trigger/oracle2-native-invented.ts'],
  ['trigger.oracle2-native-invented-v2.config.ts', 'src/trigger/oracle2-native-invented-v2.ts'],
];
for (const [config, task] of pairs) {
  const glob = readFileSync(join(workers, config), 'utf8').match(/scripts: \['([^']+)'\]/)?.[1];
  const source = readFileSync(join(workers, task), 'utf8');
  const scripts = [...source.matchAll(/(?:_SCRIPT = |python\.runScript\()'([^']+)'/g)].map(m => m[1]);
  if (!glob || !scripts.length) throw new Error(`${config}: scripts glob or script path missing`);
  const base = glob.replace(/\*\*\/\*\.py$/, '');
  for (const script of scripts) {
  if (!script.startsWith(base)) throw new Error(`${task}: ${script} is outside ${glob}`);
  if (!existsSync(join(workers, script))) throw new Error(`${task}: ${script} not found after sync`);
  console.log(`ok ${task} -> ${script}`);
  }
}

// Identity guards must match dev/oracle2/runtime-identities.yaml forbidden lists.
const forbidden = {
  'src/trigger/oracle2-native-invented.ts': ['SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL'],
  'src/trigger/oracle2-operating-model.ts': ['ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL','SUPABASE_SERVICE_ROLE_KEY'],
  'src/trigger/oracle2-run.ts': ['ORACLE2_CONFIRMED_GRAPH_URL', 'ORACLE2_PROJECTION_SIGNING_KEY',
    'ORACLE2_CHECKPOINT_DATABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'],
  'src/trigger/oracle2-project.ts': ['ORACLE2_CANDIDATE_GRAPH_URL',
    'ORACLE2_CHECKPOINT_DATABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'],
  'src/trigger/oracle2-holistic.ts': ['ORACLE2_CONFIRMED_GRAPH_URL', 'ORACLE2_PROJECTION_SIGNING_KEY',
    'ORACLE2_CHECKPOINT_DATABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'],
};
for (const [task, names] of Object.entries(forbidden)) {
  const guard = readFileSync(join(workers, task), 'utf8').split('forbidden credentials')[0];
  for (const name of names) {
    if (!guard.includes(`process.env.${name}`)) throw new Error(`${task}: guard misses ${name}`);
  }
}
// V2 uses an explicit presence-based validator so even empty forbidden values
// are denied. Keep this independently enumerated scope and require the actual
// task handler to call its validator before starting Python.
const v2 = readFileSync(join(workers, 'src/trigger/oracle2-native-invented-v2.ts'), 'utf8');
const v2Forbidden = ['ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY','ZHIPU_API_KEY','AZURE_OPENAI_API_KEY','ORACLE2_NATIVE_TRIGGER_BUNDLE','ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256','ORACLE2_PREVIEW_ADMIN_URL','ORACLE_NATIVE_ADMIN_URL','DATABASE_URL','ORACLE2_DATABASE_URL','TRIGGER_ACCESS_TOKEN','ORACLE2_PROJECTOR_GRAPH_URL','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL','ORACLE_NATIVE_GRAPH_PROJECTOR_PASSWORD','ORACLE_NATIVE_PROJECTOR_DATABASE_URL','ORACLE2_PROJECTOR_DATABASE_URL','TRIGGER_PAT'];
const list = v2.match(/const forbidden=\[([^\]]+)\];/)?.[1];
if (!list || v2Forbidden.some(name => !list.includes("'"+name+"'"))
    || !v2.includes("forbidden.some(k=>env[k]!==undefined)")) {
  throw new Error('native v2 must refuse every old/privileged variable by presence');
}
const invocation=v2.indexOf('validateNativeV2Payload(payload);');
const execution=v2.indexOf('python.runScript(');
if (invocation<0 || execution<0 || invocation>=execution) {
  throw new Error('native v2 must validate identity and environment before Python');
}
const legacy = readFileSync(join(workers, 'trigger.config.ts'), 'utf8');
if (!legacy.includes("'**/oracle2-run.ts'") || !legacy.includes("'**/oracle2-project.ts'")
    || !legacy.includes("'**/oracle2-native-invented-v2.ts'")
    || !legacy.includes("'**/oracle2-native-invented.ts'") || !legacy.includes("'**/oracle2-holistic.ts'") || !legacy.includes("'**/oracle2-operating-model.ts'")) {
  throw new Error('legacy trigger.config.ts must exclude Oracle 2 tasks');
}
console.log('ok identity guards and legacy exclusion');
