import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@trigger.dev/sdk/v3';
import { oracle2Python } from './oracle2-python-extension';

const project = process.env.ORACLE2_EXTRACT_TRIGGER_PROJECT_REF;
const otherProject = process.env.ORACLE2_PROJECT_TRIGGER_PROJECT_REF;
if (!project || !otherProject || project === otherProject
    || project === 'proj_wgpzsvhmsopqhvwqaycn'
    || otherProject === 'proj_wgpzsvhmsopqhvwqaycn') {
  throw new Error('Two distinct non-legacy Oracle 2 Trigger projects required');
}

// Scripts are copied into ./oracle2-python by scripts/oracle2/sync_worker_python.sh
// so the deployed path and python.runScript path share one base (this directory).
const triggerDir = fileURLToPath(new URL('./src/trigger', import.meta.url));

export default defineConfig({
  project,
  runtime: 'node-24',
  maxDuration: 600,
  logLevel: 'info',
  retries: { enabledInDev: false, default: { maxAttempts: 1 } },
  dirs: ['./src/trigger'],
  ignorePatterns: readdirSync(triggerDir)
    .filter((file) => file !== 'oracle2-run.ts')
    .map((file) => `**/${file}`),
  build: {
    extensions: [oracle2Python({
      scripts: ['./oracle2-python/oracle_brain/**/*.py'],
      requirementsFile: './oracle2-requirements.txt',
      devPythonBinaryPath: '../../services/oracle-brain/.venv/bin/python',
    })],
  },
});
