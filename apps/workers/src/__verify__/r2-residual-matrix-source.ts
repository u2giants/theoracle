import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import { scoreResponsibilityAnswerKey } from '../lib/responsibility-answer-key';

const answerKey = JSON.parse(
  readFileSync(new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url), 'utf8'),
) as { records: Array<{ role: string; action: string; object: string }> };

const mapIds = [
  '193376a7-848e-48e8-b5ec-8cca51285b3f',
  '5f1491c7-e38b-4c07-a063-121244215dda',
  '14724714-edc1-4012-a932-44cfd6c8ed23',
];

if (!process.env.PROD_DB_URL) throw new Error('PROD_DB_URL is required.');

const sql = postgres(process.env.PROD_DB_URL, { max: 1 });
try {
  for (const mapId of mapIds) {
    const rows = await sql`
      select elements_json
      from source_workflow_maps
      where id = ${mapId}::uuid
    `;
    if (rows.length !== 1) throw new Error(`Map ${mapId} was not found.`);
    const actual = (rows[0]!.elements_json as Array<Record<string, unknown>>)
      .filter((element) =>
        element.shape === 'responsibilities' && element.elementKind === 'responsibility')
      .map((element) => ({
        role: String(element.role ?? ''),
        action: String(element.action ?? ''),
        object: String(element.object ?? ''),
      }));
    console.log(JSON.stringify({ mapId, score: scoreResponsibilityAnswerKey({
      expected: answerKey.records,
      actual,
    }) }));
  }
} finally {
  await sql.end();
}
