import {readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {defineConfig} from '@trigger.dev/sdk/v3';
import {MEETING_TASK_FILES,resolveMeetingsTriggerProject} from './meeting-target-profile.mjs';
const triggerDir=fileURLToPath(new URL('./src/trigger',import.meta.url));
export default defineConfig({
 project:resolveMeetingsTriggerProject(process.env),runtime:'node-24',maxDuration:30,logLevel:'error',
 retries:{enabledInDev:false,default:{maxAttempts:1}},dirs:['./src/trigger'],
 ignorePatterns:readdirSync(triggerDir,{withFileTypes:true})
  .filter(entry=>entry.isDirectory()||!MEETING_TASK_FILES.includes(entry.name))
  .map(entry=>entry.isDirectory()?`**/${entry.name}/**`:`**/${entry.name}`),
});
