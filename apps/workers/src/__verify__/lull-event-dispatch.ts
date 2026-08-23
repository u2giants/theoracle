import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../../../..');
const worker = readFileSync(
  resolve(root, 'apps/workers/src/trigger/lull-interjection.ts'),
  'utf8',
);
const triggerHelper = readFileSync(resolve(root, 'apps/web/lib/trigger.ts'), 'utf8');
const messageRoute = readFileSync(
  resolve(root, 'apps/web/app/api/messages/route.ts'),
  'utf8',
);
const documentRoute = readFileSync(
  resolve(root, 'apps/web/app/api/documents/route.ts'),
  'utf8',
);

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

assert(
  worker.includes("import { task } from '@trigger.dev/sdk/v3';"),
  'lull-interjection must be an event-driven Trigger.dev task',
);
assert(!worker.includes('schedules.task({'), 'lull-interjection must not declare a schedule');
assert(!worker.includes("cron: '* * * * *'"), 'the every-minute cron must stay removed');
assert(
  triggerHelper.includes("delay: '60s'") &&
    triggerHelper.includes("mode: 'trailing'") &&
    triggerHelper.includes('key: `lull-interjection:${channelId}`'),
  'lull dispatch must trailing-debounce each channel for 60 seconds',
);
assert(
  messageRoute.includes('triggerLullCheck(msg.channelId, msg.id)'),
  'ordinary user messages must schedule a lull check',
);
assert(
  documentRoute.includes(
    'triggerLullCheck(attachmentMessage.channelId, attachmentMessage.id)',
  ),
  'document attachment messages must schedule a lull check',
);
assert(
  (worker.match(/latestUserMessage\?\.id !== expectedLatestUserMessageId/g) ?? []).length === 1 &&
    worker.includes("reasonCode: 'newer_user_message'"),
  'the worker must re-check the latest message immediately before posting',
);

console.log('Lull event dispatch contract passed');
