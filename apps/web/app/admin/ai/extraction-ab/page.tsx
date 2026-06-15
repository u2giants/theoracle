export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { scoreExtractionAbTest } from './_actions';
import { RunModelsForm } from './_components/run-models-form';

type ClaimLike = {
  claimType?: string;
  summary?: string;
  domains?: string[];
  impactScore?: number;
  confidenceScore?: number;
  evidence?: {
    exactQuote?: string;
    confidence?: number;
  };
} | null;

type EvalOutput = {
  claim?: ClaimLike;
  noClaimReason?: string;
} | null;

type Row = {
  review_event_id: string;
  reviewed_at: string;
  reviewer_name: string | null;
  original_claim_id: string;
  revised_claim_id: string;
  original_claim_type: string;
  original_summary: string;
  original_impact: number;
  original_confidence: number;
  original_domains: string[] | null;
  original_quote: string | null;
  revised_claim_type: string;
  revised_summary: string;
  revised_impact: number;
  revised_confidence: number;
  revised_domains: string[] | null;
  revised_quote: string | null;
  test_id: string | null;
  source_excerpt: string | null;
  gemini_3_1_output_json: EvalOutput;
  qwen_3_7_output_json: EvalOutput;
  gemini_3_1_error: string | null;
  qwen_3_7_error: string | null;
  best_variant: string | null;
  reviewer_note: string | null;
};

const VARIANT_OPTIONS = [
  { value: 'existing_gemini_2_5', label: 'Existing Gemini 2.5 claim' },
  { value: 'gemini_3_1_flash_lite', label: 'Gemini 3.1 Flash Lite' },
  { value: 'qwen_3_7_max', label: 'Qwen 3.7 Max' },
];

function domainBadges(domains: string[] | null | undefined) {
  if (!domains || domains.length === 0) return <span className="text-xs text-muted-foreground">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {domains.map((domain) => (
        <span key={domain} className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {domain}
        </span>
      ))}
    </div>
  );
}

function ClaimColumn({
  title,
  subtitle,
  claim,
  error,
}: {
  title: string;
  subtitle?: string;
  claim: ClaimLike;
  error?: string | null;
}) {
  return (
    <div className="min-w-[18rem] rounded border bg-background p-3">
      <div className="mb-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="text-[11px] text-muted-foreground">{subtitle}</p>}
      </div>
      {error ? (
        <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">{error}</p>
      ) : claim ? (
        <div className="space-y-2 text-xs">
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{claim.summary}</p>
          <div className="flex flex-wrap gap-2 text-muted-foreground">
            <span>{claim.claimType ?? 'unknown'}</span>
            <span>Impact {claim.impactScore ?? '-'}</span>
            <span>Confidence {claim.confidenceScore ?? '-'}</span>
          </div>
          {domainBadges(claim.domains)}
          {claim.evidence?.exactQuote && (
            <blockquote className="whitespace-pre-wrap border-l-2 pl-2 text-muted-foreground">
              {claim.evidence.exactQuote}
            </blockquote>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Not run yet.</p>
      )}
    </div>
  );
}

function originalClaim(row: Row): ClaimLike {
  return {
    claimType: row.original_claim_type,
    summary: row.original_summary,
    domains: row.original_domains ?? [],
    impactScore: row.original_impact,
    confidenceScore: row.original_confidence,
    evidence: row.original_quote ? { exactQuote: row.original_quote } : undefined,
  };
}

function revisedClaim(row: Row): ClaimLike {
  return {
    claimType: row.revised_claim_type,
    summary: row.revised_summary,
    domains: row.revised_domains ?? [],
    impactScore: row.revised_impact,
    confidenceScore: row.revised_confidence,
    evidence: row.revised_quote ? { exactQuote: row.revised_quote } : undefined,
  };
}

function generatedClaim(output: EvalOutput): ClaimLike {
  return output?.claim ?? null;
}

export default async function ExtractionAbPage() {
  const db = getDirectDb();
  const result = await db.execute(sql`
    SELECT
      cre.id AS review_event_id,
      cre.created_at AS reviewed_at,
      reviewer.name AS reviewer_name,
      original.id AS original_claim_id,
      replacement.id AS revised_claim_id,
      original.claim_type AS original_claim_type,
      original.summary AS original_summary,
      original.impact_score AS original_impact,
      original.confidence_score AS original_confidence,
      COALESCE(original_domains.domain_ids, ARRAY[]::text[]) AS original_domains,
      original_ev.exact_quote AS original_quote,
      replacement.claim_type AS revised_claim_type,
      replacement.summary AS revised_summary,
      replacement.impact_score AS revised_impact,
      replacement.confidence_score AS revised_confidence,
      COALESCE(revised_domains.domain_ids, ARRAY[]::text[]) AS revised_domains,
      revised_ev.exact_quote AS revised_quote,
      ab.id AS test_id,
      ab.source_excerpt,
      ab.gemini_3_1_output_json,
      ab.qwen_3_7_output_json,
      ab.gemini_3_1_error,
      ab.qwen_3_7_error,
      ab.best_variant,
      ab.reviewer_note
    FROM claim_review_events cre
    JOIN claims original ON original.id = cre.claim_id
    JOIN claims replacement ON replacement.id = cre.replacement_claim_id
    LEFT JOIN employees reviewer ON reviewer.id = cre.reviewed_by_employee_id
    LEFT JOIN claim_extraction_ab_tests ab ON ab.claim_review_event_id = cre.id
    LEFT JOIN LATERAL (
      SELECT array_agg(ctd.top_domain_id ORDER BY ctd.top_domain_id) AS domain_ids
      FROM claim_top_domains ctd
      WHERE ctd.claim_id = original.id
    ) original_domains ON true
    LEFT JOIN LATERAL (
      SELECT array_agg(ctd.top_domain_id ORDER BY ctd.top_domain_id) AS domain_ids
      FROM claim_top_domains ctd
      WHERE ctd.claim_id = replacement.id
    ) revised_domains ON true
    LEFT JOIN LATERAL (
      SELECT exact_quote
      FROM claim_evidence
      WHERE claim_id = original.id
      ORDER BY confidence DESC NULLS LAST, created_at ASC
      LIMIT 1
    ) original_ev ON true
    LEFT JOIN LATERAL (
      SELECT exact_quote
      FROM claim_evidence
      WHERE claim_id = replacement.id
      ORDER BY confidence DESC NULLS LAST, created_at ASC
      LIMIT 1
    ) revised_ev ON true
    WHERE cre.action = 'revise'
      AND replacement.status = 'approved'
    ORDER BY cre.created_at DESC
    LIMIT 25
  `);
  const rows = [...result] as unknown as Row[];
  const scoredCount = rows.filter((row) => row.best_variant).length;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Extraction A/B/C Test</h1>
        <p className="text-sm text-muted-foreground">
          Compare the existing Gemini 2.5-era claim, Gemini 3.1 Flash Lite,
          Qwen 3.7 Max, and your approved revision on the same source evidence.
          Pick the best AI output; your revision stays visible as the answer key.
          Generated outputs are stored here only and never promoted into claims.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Approved revisions</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{rows.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Tests run</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {rows.filter((row) => row.test_id).length}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Scored</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{scoredCount}</CardContent>
        </Card>
      </div>

      <div className="space-y-5">
        {rows.map((row) => (
          <Card key={row.review_event_id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-base">
                    Reviewed {new Date(row.reviewed_at).toLocaleString()}
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {row.reviewer_name ?? 'Reviewer'} revised original claim{' '}
                    <code>{row.original_claim_id.slice(0, 8)}</code>
                  </p>
                </div>
                <RunModelsForm reviewEventId={row.review_event_id} hasTest={!!row.test_id} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 xl:grid-cols-4">
                <ClaimColumn
                  title="Existing claim"
                  subtitle="Gemini 2.5-era output"
                  claim={originalClaim(row)}
                />
                <ClaimColumn
                  title="Gemini 3.1 Flash Lite"
                  subtitle="current default + correction lessons"
                  claim={generatedClaim(row.gemini_3_1_output_json)}
                  error={row.gemini_3_1_error}
                />
                <ClaimColumn
                  title="Qwen 3.7 Max"
                  subtitle="stronger comparison model"
                  claim={generatedClaim(row.qwen_3_7_output_json)}
                  error={row.qwen_3_7_error}
                />
                <ClaimColumn
                  title="My revision"
                  subtitle="reference answer, not scored"
                  claim={revisedClaim(row)}
                />
              </div>

              <form action={scoreExtractionAbTest} className="rounded border bg-muted/20 p-3">
                <input type="hidden" name="reviewEventId" value={row.review_event_id} />
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Choose the best AI-generated claim. Use your revision only as the reference.
                </p>
                <div className="flex flex-wrap gap-3 text-xs">
                  {VARIANT_OPTIONS.map((option) => (
                    <label key={option.value} className="flex items-center gap-1.5">
                      <input
                        type="radio"
                        name="bestVariant"
                        value={option.value}
                        defaultChecked={row.best_variant === option.value}
                        required
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
                <div className="mt-3 flex flex-col gap-2 md:flex-row">
                  <input
                    name="reviewerNote"
                    defaultValue={row.reviewer_note ?? ''}
                    placeholder="Optional note about why this one is best"
                    className="min-w-0 flex-1 rounded border bg-background px-2 py-1.5 text-xs"
                  />
                  <button
                    type="submit"
                    disabled={!row.test_id}
                    className="rounded bg-muted px-3 py-1.5 text-xs text-foreground hover:bg-muted/80 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Save score
                  </button>
                </div>
              </form>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
