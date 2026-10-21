import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@trigger.dev/sdk/v3';
import { resolveNativeTriggerProject } from '../../dev/oracle2/private-target-profile.mjs';
import { oracle2Python } from './oracle2-python-extension';
const project=resolveNativeTriggerProject(process.env);
const dir=fileURLToPath(new URL('./src/trigger',import.meta.url));
export default defineConfig({
  project,runtime:'node-24',maxDuration:120,logLevel:'error',
  retries:{enabledInDev:false,default:{maxAttempts:1}},dirs:['./src/trigger'],
  ignorePatterns:readdirSync(dir).filter(file=>file!=='oracle2-native-invented-v2.ts').map(file=>`**/${file}`),
  build:{extensions:[oracle2Python({scripts: ['./oracle2-python/oracle_brain/**/*.py'],
    requirementsFile:'./oracle2-requirements.txt',devPythonBinaryPath:'../../services/oracle-brain/.venv/bin/python'})]},
});
