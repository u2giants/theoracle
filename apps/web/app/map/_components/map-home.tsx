'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { brainGet, type CommunityCard, type Finding } from './brain';
import { LoadState, Markdown, SourceChip, StanceBadge } from './bits';

type Company = {
  id: string;
  title: string;
  summary: string;
  report_md: string;
  issues: Finding[];
};

export function MapHome() {
  const [company, setCompany] = useState<Company | null>(null);
  const [cards, setCards] = useState<CommunityCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      brainGet<{ company: Company | null }>('map/company'),
      brainGet<{ communities: CommunityCard[] }>('communities?level=1'),
    ])
      .then(([companyBody, cardBody]) => {
        if (cancelled) return;
        setCompany(companyBody.company);
        setCards(cardBody.communities);
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
          <Link className="underline" href="/map/eval">
            Evaluation
          </Link>
          <Link className="underline" href="/map/questions">
            Open questions
          </Link>
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
        <section className="grid content-start gap-3 sm:grid-cols-2" data-testid="community-cards">
          {cards.map((card) => (
            <Link
              key={card.id}
              href={`/map/community/${card.id}`}
              data-testid="community-card"
              data-community-id={card.id}
              className="block"
            >
              <Card className="h-full transition hover:border-foreground/40">
                <CardHeader>
                  <CardTitle className="text-base">{card.title}</CardTitle>
                  <CardDescription>
                    {card.finding_count} finding{card.finding_count === 1 ? '' : 's'} ·{' '}
                    {card.entity_count} things
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="line-clamp-4 text-sm text-muted-foreground">{card.summary}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </section>
      </div>
    </main>
  );
}
