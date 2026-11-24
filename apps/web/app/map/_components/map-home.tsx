'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { brainGet, type Finding } from './brain';
import { LoadState, Markdown, SourceChip, StanceBadge } from './bits';

// Repair C5: the map page is organised by business function. Left stays the
// company report; the centre column is one card per curated function with its
// counts and the open issues known today (disagreements and gaps). The F6
// coverage score is not landed, so no score is shown yet.

type Company = {
  id: string;
  title: string;
  summary: string;
  report_md: string;
  issues: Finding[];
};

type FunctionCardData = {
  id: string;
  key: string;
  name: string;
  description: string;
  report_id: string | null;
  summary: string;
  entity_count: number;
  source_count: number;
  process_count: number;
  person_count: number;
  open_contradictions: number;
  open_gaps: number;
  top_issues: { text: string; kind: string }[];
};

function issueLabel(kind: string): string {
  return kind === 'contradiction' ? 'disagreement' : 'gap';
}

export function MapHome({ isAdmin }: { isAdmin: boolean }) {
  const [company, setCompany] = useState<Company | null>(null);
  const [cards, setCards] = useState<FunctionCardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      brainGet<{ company: Company | null }>('map/company'),
      brainGet<{ functions: FunctionCardData[] }>('map/functions'),
    ])
      .then(([companyBody, cardBody]) => {
        if (cancelled) return;
        setCompany(companyBody.company);
        setCards(cardBody.functions);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'load failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Company Map</h1>
        <nav className="flex gap-4 text-sm">
          <Link className="underline" href="/map/ask">
            Ask the map
          </Link>
          <Link className="underline" href="/map/sources">
            Sources
          </Link>
          {isAdmin && (
            <Link className="underline" href="/map/meetings">
              Meetings
            </Link>
          )}
          <Link className="underline" href="/map/recommendations">
            Recommendations
          </Link>
          <Link className="underline" href="/map/eval">
            Evaluation
          </Link>
          <Link className="underline" href="/map/questions">
            Open questions
          </Link>
          <Link className="underline" href="/map/functions" data-testid="functions-link">
            Functions
          </Link>
          <Link
            className="underline"
            href="/map/contradictions"
            data-testid="contradictions-link"
          >
            Contradictions
          </Link>
          {isAdmin && (
            <Link className="underline" href="/map/review" data-testid="review-link">
              Review flags
            </Link>
          )}
        </nav>
      </header>
      <LoadState error={error} loading={loading} />
      {!loading && !error && !company && cards.length === 0 && (
        <p className="text-sm text-muted-foreground">
          The map is empty. Add sources, then rebuild the map from the Sources page.
        </p>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section data-testid="company-report" className="space-y-4">
          {company && (
            <>
              <h2 className="text-lg font-semibold">{company.title}</h2>
              <Markdown text={company.summary} />
              <div>
                <h2 className="mb-2 font-semibold">Top issues</h2>
                <ol className="list-decimal space-y-2 pl-5" data-testid="top-issues">
                  {company.issues.map((issue, index) => (
                    <li key={`${index}-${issue.text}`} className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span>{issue.text}</span>
                        <StanceBadge stance={issue.stance} />
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {issue.sources.map((source) => (
                          <SourceChip key={source.id} source={source} />
                        ))}
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </>
          )}
        </section>
        <section className="grid content-start gap-3 sm:grid-cols-2" data-testid="function-cards">
          {cards.map((card) => (
            <Link
              key={card.id}
              href={`/map/function/${encodeURIComponent(card.key)}`}
              data-testid="function-card"
              data-function-id={card.id}
              data-function-key={card.key}
              className="block"
            >
              <Card className="h-full transition hover:border-foreground/40">
                <CardHeader>
                  <CardTitle className="text-base">{card.name}</CardTitle>
                  <CardDescription>
                    {card.source_count} source{card.source_count === 1 ? '' : 's'} ·{' '}
                    {card.entity_count} thing{card.entity_count === 1 ? '' : 's'} ·{' '}
                    {card.process_count} process{card.process_count === 1 ? '' : 'es'} ·{' '}
                    {card.person_count} {card.person_count === 1 ? 'person' : 'people'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="line-clamp-3 text-sm text-muted-foreground">
                    {card.summary || card.description}
                  </p>
                  {(card.open_contradictions > 0 || card.open_gaps > 0) && (
                    <p className="text-xs text-muted-foreground" data-testid="function-card-open">
                      {card.open_contradictions} open{' '}
                      {card.open_contradictions === 1 ? 'disagreement' : 'disagreements'} ·{' '}
                      {card.open_gaps} open {card.open_gaps === 1 ? 'gap' : 'gaps'}
                    </p>
                  )}
                  {card.top_issues.length > 0 && (
                    <ul className="space-y-1" data-testid="function-card-issues">
                      {card.top_issues.map((issue, index) => (
                        <li
                          key={`${index}-${issue.text}`}
                          className="flex items-start gap-1.5 text-xs text-muted-foreground"
                          data-testid="function-card-issue"
                          data-issue-kind={issue.kind}
                        >
                          <span className="mt-0.5 shrink-0 rounded bg-muted px-1.5 py-0.5">
                            {issueLabel(issue.kind)}
                          </span>
                          <span className="line-clamp-2">{issue.text}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </section>
      </div>
    </main>
  );
}
