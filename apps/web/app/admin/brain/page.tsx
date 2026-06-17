export const dynamic = 'force-dynamic';

import { desc, eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { brainSections, brainSectionVersions } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

function reviewBadge(status: string) {
  const map: Record<string, string> = {
    draft: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    needs_review: 'bg-orange-100 text-orange-800',
    rejected: 'bg-red-100 text-red-800',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminBrainPage() {
  const db = getDirectDb();

  const rows = await db
    .select({
      sectionId: brainSections.id,
      title: brainSections.title,
      knowledgeDomain: brainSections.knowledgeDomain,
      category: brainSections.category,
      sectionUpdatedAt: brainSections.updatedAt,
      versionId: brainSectionVersions.id,
      versionNumber: brainSectionVersions.versionNumber,
      markdown: brainSectionVersions.markdown,
      changeSummary: brainSectionVersions.changeSummary,
      reviewStatus: brainSectionVersions.reviewStatus,
      reviewedAt: brainSectionVersions.reviewedAt,
      versionCreatedAt: brainSectionVersions.createdAt,
    })
    .from(brainSections)
    .leftJoin(
      brainSectionVersions,
      eq(brainSectionVersions.id, brainSections.currentVersionId),
    )
    .orderBy(desc(brainSections.updatedAt));

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Brain</h1>
        <p className="text-sm text-muted-foreground">
          Versioned knowledge sections synthesized by the brain-synthesis worker from
          approved claims. Each section covers one knowledge domain.
        </p>
      </header>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            <p>No brain sections yet.</p>
            <p className="mt-1">
              The brain-synthesis worker generates sections once claims are approved.
              Approve claims on the{' '}
              <a href="/admin/claims" className="underline hover:no-underline">
                Claims tab
              </a>{' '}
              to unblock synthesis.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">{rows.length} sections</p>
          {rows.map((row) => (
            <Card key={row.sectionId}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-base">{row.title}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {row.knowledgeDomain} · {row.category}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 text-xs">
                    {row.versionNumber != null && (
                      <span className="text-muted-foreground">v{row.versionNumber}</span>
                    )}
                    {row.reviewStatus && (
                      <span
                        className={`rounded px-2 py-0.5 font-medium ${reviewBadge(row.reviewStatus)}`}
                      >
                        {row.reviewStatus.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {row.versionId == null ? (
                  <p className="italic text-xs text-muted-foreground">
                    No version synthesized yet.
                  </p>
                ) : (
                  <>
                    {row.changeSummary && (
                      <p className="text-xs text-muted-foreground">
                        <span className="font-medium">Change summary:</span>{' '}
                        {row.changeSummary}
                      </p>
                    )}
                    <div className="max-h-64 overflow-y-auto rounded border bg-muted/40 p-3">
                      <pre className="whitespace-pre-wrap text-xs leading-relaxed">
                        {row.markdown}
                      </pre>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Synthesized{' '}
                      {row.versionCreatedAt
                        ? formatNYDateTime(row.versionCreatedAt)
                        : '—'}
                      {row.reviewedAt && (
                        <>
                          {' · '}reviewed {formatNYDateTime(row.reviewedAt)}
                        </>
                      )}
                    </p>
                  </>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
