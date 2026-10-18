import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@trigger.dev/sdk/v3';
import { oracle2Python } from './oracle2-python-extension';
const customProject=process.env.ORACLE2_NATIVE_TRIGGER_PROJECT_REF;
const officialProject=process.env.TRIGGER_PROJECT_REF;
// The official index worker deliberately receives only runtime variables, not
// its controller's project env. The source-pinned target is the default; any
// explicit override must still equal that exact isolated target.
const project=customProject??officialProject??'proj_jtaztxnmppzfchdsgvea';
if (project!=='proj_jtaztxnmppzfchdsgvea'||(customProject!==undefined&&officialProject!==undefined&&customProject!==officialProject))
  throw new Error('Exact dedicated isolated native proof project required');
const dir=fileURLToPath(new URL('./src/trigger',import.meta.url));
export default defineConfig({
  project,runtime:'node-24',maxDuration:120,logLevel:'error',
  retries:{enabledInDev:false,default:{maxAttempts:1}},dirs:['./src/trigger'],
  ignorePatterns:readdirSync(dir).filter(file=>file!=='oracle2-native-invented-v2.ts').map(file=>`**/${file}`),
  build:{extensions:[oracle2Python({scripts: ['./oracle2-python/oracle_brain/**/*.py'],
    requirementsFile:'./oracle2-requirements.txt',devPythonBinaryPath:'../../services/oracle-brain/.venv/bin/python'})]},
});
