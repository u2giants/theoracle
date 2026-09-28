import { readdirSync } from 'node:fs';
import { defineConfig } from '@trigger.dev/sdk/v3';
import { pythonExtension } from '@trigger.dev/python/extension';

const project = process.env.ORACLE2_PROJECT_TRIGGER_PROJECT_REF;
const extractorProject = process.env.ORACLE2_EXTRACT_TRIGGER_PROJECT_REF;
if (!project || !extractorProject || project === extractorProject
    || project === 'proj_wgpzsvhmsopqhvwqaycn'
    || extractorProject === 'proj_wgpzsvhmsopqhvwqaycn') {
  throw new Error('Two distinct non-legacy Oracle 2 Trigger projects required');
}

export default defineConfig({
  project,
  runtime: 'node-24',
  maxDuration: 600,
  dirs: ['./src/trigger'],
  ignorePatterns: readdirSync('./src/trigger')
    .filter((file) => file !== 'oracle2-project.ts')
    .map((file) => `**/${file}`),
  build: {
    extensions: [pythonExtension({
      scripts: ['../../services/oracle-brain/oracle_brain/**/*.py'],
      requirementsFile: './oracle2-requirements.txt',
      devPythonBinaryPath: '../../services/oracle-brain/.venv/bin/python',
    })],
  },
});
