import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import { sql } from 'drizzle-orm';
import { config as loadEnv } from 'dotenv';
import * as schema from '@oracle/db/schema';
import { embedMany } from '../embeddings';
import { searchWithRetrievalPlan } from '../retrieval';
import { buildRetrievalPlanFromQuery } from '../retrieval-plan';

const fixtures = [
  { query: '样品批准后谁通知供应商', relevant: '样品获得批准后，采购经理通知供应商开始生产。' },
  { query: '设计文件放在哪里', relevant: '最终设计文件必须保存在 Designflow 的已批准文件夹中。' },
  { query: '客户更改订单怎么办', relevant: '客户更改订单后，销售人员必须更新订单并通知计划团队。' },
  { query: '什么时候检查包装', relevant: '包装在量产开始前由质量团队检查。' },
  { query: '谁批准许可方图稿', relevant: '许可方图稿由品牌经理提交给许可方批准。' },
] as const;

const distractors = [
  '财务团队每周核对供应商发票。',
  '员工应在休假前更新共享日历。',
  '仓库在收到货物后记录箱数。',
];

type TranslationFixture = {
  status: 'pending_review' | 'approved' | 'rejected';
  sourceHashMatches: boolean;
};

type LivePositiveFixture = {
  label: string;
  query: string;
  expectedClaimId: string;
};

type LiveNegativeFixture = {
  label: string;
  query: string;
  excludedClaimIds: string[];
};

type LiveFixtureContract = {
  positives: LivePositiveFixture[];
  negatives: LiveNegativeFixture[];
};

const MIN_LABELED_PRODUCTION_FIXTURES = 5;

function safeLabel(label: string): string {
  assert(
    /^[a-z0-9][a-z0-9_-]{0,63}$/u.test(label),
    'Fixture labels must contain only lowercase letters, numbers, underscores, or hyphens.',
  );
  return label;
}

function safeQueryId(query: string): string {
  return createHash('sha256').update(normalizeQuery(query)).digest('hex').slice(0, 12);
}

function normalizeQuery(query: string): string {
  return query.normalize('NFKC').trim().replace(/\s+/gu, ' ').toLocaleLowerCase('zh-CN');
}

function parseLiveFixtureContract(): LiveFixtureContract {
  const raw = process.env.GAP4_CHINESE_RETRIEVAL_FIXTURES_JSON;
  if (!raw) return { positives: [], negatives: [] };
  const value = JSON.parse(raw) as Partial<LiveFixtureContract>;
  assert(Array.isArray(value.positives), 'Live fixture contract positives must be an array.');
  assert(Array.isArray(value.negatives), 'Live fixture contract negatives must be an array.');
  return {
    positives: value.positives.map((fixture) => ({
      label: safeLabel(fixture.label),
      query: String(fixture.query ?? '').trim(),
      expectedClaimId: String(fixture.expectedClaimId ?? ''),
    })),
    negatives: value.negatives.map((fixture) => ({
      label: safeLabel(fixture.label),
      query: String(fixture.query ?? '').trim(),
      excludedClaimIds: Array.isArray(fixture.excludedClaimIds)
        ? fixture.excludedClaimIds.map(String)
        : [],
    })),
  };
}

async function searchWithoutQueryLogging(
  db: Parameters<typeof searchWithRetrievalPlan>[0],
  query: string,
) {
  const plan = buildRetrievalPlanFromQuery(query);
  plan.topK = 3;
  // The labeled production set below uses this same "current" filter.
  plan.timeFilter = 'current';
  const originalWarn = console.warn;
  console.warn = (...args: unknown[]) => {
    if (args[0] === '[oracle:retrieval] global_fallback — searching entire claim corpus') return;
    originalWarn(...args);
  };
  try {
    return await searchWithRetrievalPlan(db, plan, 'zh-CN');
  } finally {
    console.warn = originalWarn;
  }
}

function canServeTranslation(translation: TranslationFixture): boolean {
  return translation.status === 'approved' && translation.sourceHashMatches;
}

function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let aa = 0;
  let bb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!;
    aa += a[i]! * a[i]!;
    bb += b[i]! * b[i]!;
  }
  return aa === 0 || bb === 0 ? 0 : dot / Math.sqrt(aa * bb);
}

function simpleSearchMatches(query: string, text: string): boolean {
  // PostgreSQL's `simple` configuration does not segment Chinese words. This
  // deliberately conservative proxy counts only a contiguous query match.
  return text.includes(query);
}

async function main() {
  const requireLive = process.argv.includes('--require-live');
  if (requireLive) {
    const envPath = resolve(process.cwd(), '..', '..', '.env.gap4.local');
    assert(existsSync(envPath), 'explicit .env.gap4.local is required; refusing ambient credentials');
    loadEnv({ path: envPath, override: true, quiet: true });
  }
  const servingCases: Array<{ name: string; input: TranslationFixture; expected: boolean }> = [
    {
      name: 'approved current translation',
      input: { status: 'approved', sourceHashMatches: true },
      expected: true,
    },
    {
      name: 'pending translation',
      input: { status: 'pending_review', sourceHashMatches: true },
      expected: false,
    },
    {
      name: 'rejected translation',
      input: { status: 'rejected', sourceHashMatches: true },
      expected: false,
    },
    {
      name: 'stale approved translation',
      input: { status: 'approved', sourceHashMatches: false },
      expected: false,
    },
  ];
  for (const fixture of servingCases) {
    if (canServeTranslation(fixture.input) !== fixture.expected) {
      throw new Error(`translation serving fixture failed: ${fixture.name}`);
    }
  }
  console.log('translation serving: pending, rejected, and stale rows excluded');

  const simpleHits = fixtures.filter((fixture) =>
    simpleSearchMatches(fixture.query, fixture.relevant),
  ).length;
  console.log(`simple search recall: ${simpleHits}/${fixtures.length}`);

  if (!requireLive) {
    console.log('vector recall: skipped (use verify:chinese-retrieval-live)');
    console.log('PASS: simple-search measurement recorded; live vector gate remains explicit.');
    return;
  }
  if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY is required for the live Chinese vector fixture.');
  }

  const databaseUrl = process.env.DATABASE_URL;
  assert(databaseUrl, 'DATABASE_URL is required in .env.gap4.local.');
  assert(
    databaseUrl.includes('eqccjfbyrywsqkxxpjvg'),
    'Refusing database target: expected current production project eqccjfbyrywsqkxxpjvg.',
  );

  const corpus = [...fixtures.map((fixture) => fixture.relevant), ...distractors];
  const { vectors: corpusVectors, fallback } = await embedMany(corpus);
  const { vectors: queryVectors } = await embedMany(fixtures.map((fixture) => fixture.query));
  if (fallback) throw new Error('Live Chinese vector fixture received fallback embeddings.');

  let vectorHits = 0;
  for (let i = 0; i < fixtures.length; i++) {
    const ranked = corpusVectors
      .map((vector, corpusIndex) => ({ corpusIndex, score: cosine(queryVectors[i]!, vector) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 3);
    if (ranked.some((item) => item.corpusIndex === i)) vectorHits += 1;
  }
  const recall = vectorHits / fixtures.length;
  console.log(`vector recall@3: ${vectorHits}/${fixtures.length} (${(recall * 100).toFixed(0)}%)`);
  if (recall < 0.8) {
    throw new Error('Chinese vector recall fell below the 80% fixture gate.');
  }

  const client = postgres(databaseUrl, { max: 1, prepare: false });
  const db = drizzle(client, { schema });
  try {
    const liveRows = await db.execute<{
      claim_id: string;
      summary: string;
    }>(sql`
      SELECT ct.claim_id, ct.summary
      FROM claim_translations ct
      JOIN claims c ON c.id = ct.claim_id
      LEFT JOIN claim_metadata cm ON cm.claim_id = c.id
      WHERE ct.lang = 'zh-CN'
        AND ct.review_status = 'approved'
        AND ct.source_hash = encode(digest(c.summary, 'sha256'), 'hex')
        AND ct.embedding IS NOT NULL
        AND c.status = 'approved'
        AND (cm.claim_id IS NULL OR cm.effective_until IS NULL)
      ORDER BY ct.updated_at DESC, ct.claim_id
    `);
    const contract = parseLiveFixtureContract();
    const eligibleById = new Map(liveRows.map((row) => [row.claim_id, row]));
    const normalizedPositiveQueries = contract.positives.map((fixture) =>
      normalizeQuery(fixture.query)
    );
    assert(
      new Set(normalizedPositiveQueries).size === normalizedPositiveQueries.length,
      'Positive fixture queries must be unique after Unicode and whitespace normalization.',
    );
    const positiveQueryIds = contract.positives.map((fixture) => safeQueryId(fixture.query));
    assert(
      new Set(positiveQueryIds).size === positiveQueryIds.length,
      'Positive fixture query IDs must be unique.',
    );
    const expectedClaimIds = contract.positives.map((fixture) => fixture.expectedClaimId);
    assert(
      new Set(expectedClaimIds).size === expectedClaimIds.length,
      'Positive fixtures must target distinct eligible production claims.',
    );
    for (const fixture of contract.negatives) {
      for (const excludedClaimId of fixture.excludedClaimIds) {
        assert(
          eligibleById.has(excludedClaimId),
          `Negative fixture ${fixture.label} names an excluded claim outside the retrievable production set.`,
        );
      }
    }
    const sampleSufficient =
      contract.positives.length >= MIN_LABELED_PRODUCTION_FIXTURES &&
      contract.negatives.length >= 1;
    if (!sampleSufficient) {
      console.log(JSON.stringify({
        databaseProjectRefVerified: true,
        productionWrites: 0,
        eligibleProductionTranslations: liveRows.length,
        independentlyLabeledPositiveFixtures: contract.positives.length,
        requiredPositiveFixtures: MIN_LABELED_PRODUCTION_FIXTURES,
        unrelatedNegativeControls: contract.negatives.length,
        status: 'insufficient_production_sample',
        extensionNeeded: 'unproven',
      }, null, 2));
      throw new Error(
        'insufficient_production_sample: five independent labeled queries and one negative control are required.',
      );
    }

    let liveVectorHits = 0;
    let liveSimpleHits = 0;
    const rankings: Array<{
      label: string;
      queryId: string;
      expectedRank: number | null;
      simpleMatch: boolean;
      localizedSummaryMatched: boolean;
    }> = [];
    for (const fixture of contract.positives) {
      assert(fixture.query.length >= 4, `Fixture ${fixture.label} query is too short.`);
      const expected = eligibleById.get(fixture.expectedClaimId);
      assert(expected, `Fixture ${fixture.label} target is not an eligible production translation.`);
      assert(
        !expected.summary.includes(fixture.query) && !fixture.query.includes(expected.summary),
        `Fixture ${fixture.label} is circular: query and target must not contain one another.`,
      );
      const results = await searchWithoutQueryLogging(db, fixture.query);
      const expectedRank = results.findIndex((row) => row.id === expected.claim_id);
      const localizedSummaryMatched =
        expectedRank >= 0 && results[expectedRank]?.summary === expected.summary;
      if (expectedRank >= 0) {
        assert(
          localizedSummaryMatched,
          `Fixture ${fixture.label} returned the target claim without its approved Chinese summary.`,
        );
      }
      if (expectedRank >= 0 && localizedSummaryMatched) liveVectorHits++;

      const [simpleResult] = await db.execute<{ matched: boolean }>(sql`
        SELECT
          to_tsvector('simple', ${expected.summary})
          @@ plainto_tsquery('simple', ${fixture.query}) AS matched
      `);
      const simpleMatch = simpleResult?.matched === true;
      if (simpleMatch) liveSimpleHits++;
      rankings.push({
        label: fixture.label,
        queryId: safeQueryId(fixture.query),
        expectedRank: expectedRank >= 0 ? expectedRank + 1 : null,
        simpleMatch,
        localizedSummaryMatched,
      });
    }

    const negativeControls = [];
    for (const fixture of contract.negatives) {
      assert(fixture.query.length >= 4, `Negative fixture ${fixture.label} query is too short.`);
      assert(
        fixture.excludedClaimIds.length > 0,
        `Negative fixture ${fixture.label} must name at least one unrelated claim.`,
      );
      const results = await searchWithoutQueryLogging(db, fixture.query);
      const returnedIds = new Set(results.map((row) => row.id));
      const excludedHit = fixture.excludedClaimIds.some((id) => returnedIds.has(id));
      negativeControls.push({
        label: fixture.label,
        queryId: safeQueryId(fixture.query),
        excludedClaimInTop3: excludedHit,
      });
      assert(!excludedHit, `Negative fixture ${fixture.label} returned an excluded claim in the top 3.`);
    }

    const liveRecall = liveVectorHits / contract.positives.length;
    const vectorGatePassed = liveRecall >= 0.8;
    console.log(JSON.stringify({
      databaseProjectRefVerified: true,
      productionWrites: 0,
      eligibleProductionTranslations: liveRows.length,
      independentlyLabeledPositiveFixtures: contract.positives.length,
      actualProductionPath: 'searchWithRetrievalPlan(locale=zh-CN)',
      ranking: rankings,
      negativeControls,
      vectorRecallAt3: {
        hits: liveVectorHits,
        total: contract.positives.length,
        recall: liveRecall,
      },
      simpleSearchRecall: {
        hits: liveSimpleHits,
        total: contract.positives.length,
        recall: liveSimpleHits / contract.positives.length,
        segmentationFailureObserved: liveSimpleHits < contract.positives.length,
      },
      status: vectorGatePassed ? 'passed' : 'failed',
      extensionNeeded: vectorGatePassed ? false : 'unproven',
    }, null, 2));
    assert(vectorGatePassed, 'Production Chinese retrieval recall@3 fell below the 80% gate.');
  } finally {
    await client.end({ timeout: 5 });
  }
  console.log('PASS: independently labeled production Chinese retrieval meets every live gate.');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
