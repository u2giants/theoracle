import { readdirSync } from 'node:fs';
import { defineConfig } from '@trigger.dev/sdk/v3';
import { pythonExtension } from '@trigger.dev/python/extension';

const project = process.env.ORACLE2_EXTRACT_TRIGGER_PROJECT_REF;
if (!project || project === 'proj_wgpzsvhmsopqhvwqaycn') {
  throw new Error('Dedicated Oracle 2 extractor Trigger project required');
}

export default defineConfig({
  project,
  runtime: 'node-24',
  maxDuration: 600,
  dirs: ['./src/trigger'],
  ignorePatterns: readdirSync('./src/trigger')
    .filter((file) => file !== 'oracle2-run.ts')
    .map((file) => `**/${file}`),
  build: {
    extensions: [pythonExtension({
      scripts: ['../../services/oracle-brain/oracle_brain/**/*.py'],
      requirementsFile: '../../services/oracle-brain/requirements.txt',
    })],
  },
});
