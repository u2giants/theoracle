import { desc, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { recommendations } from '@oracle/db/schema';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

export const dynamic = 'force-dynamic';

export default async function AdminRecommendationsPage() {
  const db = getDirectDb();
  const [countRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(recommendations);

  const rows = await db
    .select({
      id: recommendations.id,
      origin: recommendations.origin,
      analyzerKey: recommendations.analyzerKey,
      title: recommendations.title,
      severity: recommendations.severity,
      narrative: recommendations.narrative,
      status: recommendations.status,
      createdAt: recommendations.createdAt,
    })
    .from(recommendations)
    .orderBy(desc(recommendations.createdAt))
    .limit(50);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Recommendations</h1>
        <p className="text-sm text-muted-foreground">
          Read-only Stage 1 surface for deterministic and synthesized consultant recommendations.
        </p>
      </header>

      <Card className="max-w-sm">
        <CardHeader>
          <CardTitle className="text-base">{countRow?.count ?? 0}</CardTitle>
          <CardDescription>Total recommendations</CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recommendation queue</CardTitle>
          <CardDescription>Stage 7 analyzers and synthesis will populate this table.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {rows.length === 0 ? (
            <p className="rounded border border-dashed px-3 py-6 text-sm text-muted-foreground">
              No recommendations yet.
            </p>
          ) : (
            rows.map((row) => (
              <div key={row.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{row.title}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{row.status}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{row.severity}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{row.origin}</span>
                  {row.analyzerKey ? (
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">
                      {row.analyzerKey}
                    </span>
                  ) : null}
                  <span className="text-xs text-muted-foreground">
                    {formatNYDateTime(row.createdAt)}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-muted-foreground">{row.narrative}</p>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
