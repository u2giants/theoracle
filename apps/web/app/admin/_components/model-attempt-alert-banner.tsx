import { and, eq, or, sql } from 'drizzle-orm';
import { TriangleAlert } from 'lucide-react';
import { getDirectDb } from '@oracle/db/client';
import { modelRunAttempts } from '@oracle/db/schema';

type AttemptSummary = {
  problemCount: number;
  failedCount: number;
  nonPrimaryCount: number;
  latestAt: Date | null;
};

export async function ModelAttemptAlertBanner() {
  const db = getDirectDb();
  const [summary] = await db
    .select({
      problemCount: sql<number>`count(*)::int`,
      failedCount: sql<number>`count(*) filter (where ${modelRunAttempts.status} <> 'success')::int`,
      nonPrimaryCount: sql<number>`count(*) filter (where ${modelRunAttempts.isPrimary} = false and ${modelRunAttempts.status} = 'success')::int`,
      latestAt: sql<Date | null>`max(${modelRunAttempts.createdAt})`,
    })
    .from(modelRunAttempts)
    .where(
      and(
        sql`${modelRunAttempts.createdAt} >= now() - interval '7 days'`,
        or(
          sql`${modelRunAttempts.status} <> 'success'`,
          and(eq(modelRunAttempts.isPrimary, false), eq(modelRunAttempts.status, 'success')),
        ),
      ),
    );

  const data = (summary ?? {
    problemCount: 0,
    failedCount: 0,
    nonPrimaryCount: 0,
    latestAt: null,
  }) as AttemptSummary;

  if (data.problemCount === 0) return null;

  const latestLabel = data.latestAt
    ? new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }).format(new Date(data.latestAt))
    : null;

  return (
    <div className="mb-6 flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <TriangleAlert className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
      <div>
        <div className="font-medium">Recent model routing attention needed</div>
        <div className="text-amber-900">
          Last 7 days: {data.failedCount} failed attempt{data.failedCount === 1 ? '' : 's'}
          {data.nonPrimaryCount > 0
            ? ` and ${data.nonPrimaryCount} non-primary success${data.nonPrimaryCount === 1 ? '' : 'es'}`
            : ''}
          {latestLabel ? `; latest ${latestLabel}.` : '.'}
        </div>
      </div>
    </div>
  );
}
