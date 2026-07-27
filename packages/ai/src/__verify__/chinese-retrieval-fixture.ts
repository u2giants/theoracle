import { embedMany } from '../embeddings';

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

  if (!process.argv.includes('--require-live')) {
    console.log('vector recall: skipped (use verify:chinese-retrieval-live)');
    console.log('PASS: simple-search measurement recorded; live vector gate remains explicit.');
    return;
  }
  if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY is required for the live Chinese vector fixture.');
  }

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
  console.log('PASS: Chinese vector plus simple retrieval meets the fixture gate.');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
