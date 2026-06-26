/**
 * file-part-translation.ts — pure guard proving the provider-neutral FILE part
 * (`{ type:'file', mimeType, data, fileName? }`, e.g. a chat PDF attachment) is
 * translated to each provider's native document shape at dispatch. Before this,
 * the neutral file part had no translator and was silently dropped/mis-shaped by
 * every adapter (chat PDF attachments did not reach the model).
 *
 * Run: corepack pnpm --filter @oracle/ai exec tsx src/__verify__/file-part-translation.ts
 */
import { isNeutralFilePart, toOpenAIContent, toAnthropicContent } from '../providers/cache-utils';

let failures = 0;
function check(name: string, cond: boolean): void {
  console.log(`  ${cond ? '✓' : '✗'} ${name}`);
  if (!cond) failures++;
}

const filePart = { type: 'file', mimeType: 'application/pdf', data: 'QkFTRTY0', fileName: 'spec.pdf' };
const imagePart = { type: 'image', mimeType: 'image/png', data: 'aW1n' };
const textPart = { type: 'text', text: 'hello' };
const content = [textPart, imagePart, filePart];

console.log('isNeutralFilePart — detector:');
check('flags a neutral PDF file part', isNeutralFilePart(filePart));
check('does NOT flag an image part', !isNeutralFilePart(imagePart));
check('does NOT flag a text part', !isNeutralFilePart(textPart));
check('does NOT flag an already-translated OpenAI file part', !isNeutralFilePart({ type: 'file', file: { filename: 'x', file_data: 'y' } }));

console.log('\ntoOpenAIContent — OpenAI/Qwen/DeepSeek:');
const oai = toOpenAIContent(content) as Array<Record<string, unknown>>;
check('text passes through', (oai[0] as { type: string }).type === 'text');
check('image → image_url', (oai[1] as { type: string }).type === 'image_url');
const oaiFile = oai[2] as { type: string; file?: { filename?: string; file_data?: string } };
check('file → openai file part', oaiFile.type === 'file');
check('carries filename', oaiFile.file?.filename === 'spec.pdf');
check('file_data is a base64 data URL', oaiFile.file?.file_data === 'data:application/pdf;base64,QkFTRTY0');

console.log('\ntoAnthropicContent — Anthropic:');
const ant = toAnthropicContent(content) as Array<Record<string, unknown>>;
check('image → image block', (ant[1] as { type: string }).type === 'image');
const antFile = ant[2] as { type: string; source?: { type?: string; media_type?: string; data?: string } };
check('file → document block', antFile.type === 'document');
check('base64 source with media_type', antFile.source?.type === 'base64' && antFile.source?.media_type === 'application/pdf');
check('data preserved', antFile.source?.data === 'QkFTRTY0');

console.log(`\n${failures === 0 ? 'PASS — neutral file parts translate for every provider' : `${failures} FAILED`}`);
process.exit(failures === 0 ? 0 : 1);
