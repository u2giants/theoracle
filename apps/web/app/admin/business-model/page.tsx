import { desc, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { businessModelChanges, businessProcesses, sourceWorkflowMaps } from '@oracle/db/schema';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

export const dynamic = 'force-dynamic';

async function countRows(
  db: ReturnType<typeof getDirectDb>,
  table: typeof businessProcesses | typeof businessModelChanges | typeof sourceWorkflowMaps,
): Promise<number> {
  const [row] = await db.select({ count: sql<number>`count(*)::int` }).from(table);
  return row?.count ?? 0;
}

function EmptyState({ label }: { label: string }) {
  return (
    <p className="rounded border border-dashed px-3 py-6 text-sm text-muted-foreground">
      No {label} yet.
    </p>
  );
}

export default async function AdminBusinessModelPage() {
  const db = getDirectDb();

  const [processCount, proposalCount, mapCount, processes, proposals, maps] = await Promise.all([
    countRows(db, businessProcesses),
    countRows(db, businessModelChanges),
    countRows(db, sourceWorkflowMaps),
    db
      .select({
        id: businessProcesses.id,
        name: businessProcesses.name,
        status: businessProcesses.status,
        summary: businessProcesses.summary,
        currentVersionId: businessProcesses.currentVersionId,
        updatedAt: businessProcesses.updatedAt,
      })
      .from(businessProcesses)
      .orderBy(desc(businessProcesses.updatedAt))
      .limit(20),
    db
      .select({
        id: businessModelChanges.id,
        changeType: businessModelChanges.changeType,
        status: businessModelChanges.status,
        summary: businessModelChanges.summary,
        sourceWorkflowMapId: businessModelChanges.sourceWorkflowMapId,
        createdAt: businessModelChanges.createdAt,
      })
      .from(businessModelChanges)
      .orderBy(desc(businessModelChanges.createdAt))
      .limit(20),
    db
      .select({
        id: sourceWorkflowMaps.id,
        sourceType: sourceWorkflowMaps.sourceType,
        status: sourceWorkflowMaps.status,
        documentShape: sourceWorkflowMaps.documentShape,
        mapKind: sourceWorkflowMaps.mapKind,
        summary: sourceWorkflowMaps.summary,
        createdAt: sourceWorkflowMaps.createdAt,
      })
      .from(sourceWorkflowMaps)
      .orderBy(desc(sourceWorkflowMaps.createdAt))
      .limit(20),
  ]);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Business Model</h1>
        <p className="text-sm text-muted-foreground">
          Read-only surface for source structure maps, model-change proposals, and durable business
          processes.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{mapCount}</CardTitle>
            <CardDescription>Source structure maps</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{proposalCount}</CardTitle>
            <CardDescription>Model-change proposals</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{processCount}</CardTitle>
            <CardDescription>Business processes</CardDescription>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Business processes</CardTitle>
          <CardDescription>
            Approved versions will become the primary answering context.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {processes.length === 0 ? (
            <EmptyState label="business processes" />
          ) : (
            processes.map((process) => (
              <div key={process.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{process.name}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{process.status}</span>
                  <span className="text-xs text-muted-foreground">
                    updated {formatNYDateTime(process.updatedAt)}
                  </span>
                </div>
                {process.summary ? (
                  <p className="mt-2 text-muted-foreground">{process.summary}</p>
                ) : null}
                {process.currentVersionId ? (
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    current version {process.currentVersionId}
                  </p>
                ) : null}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model-change proposals</CardTitle>
          <CardDescription>Stage 4 will populate this queue in shadow mode.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {proposals.length === 0 ? (
            <EmptyState label="model-change proposals" />
          ) : (
            proposals.map((proposal) => (
              <div key={proposal.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">
                    {proposal.changeType}
                  </span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{proposal.status}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatNYDateTime(proposal.createdAt)}
                  </span>
                </div>
                <p className="mt-2">{proposal.summary ?? 'No summary'}</p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  map {proposal.sourceWorkflowMapId}
                </p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Source structure maps</CardTitle>
          <CardDescription>Validated per-source structure maps are written here.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {maps.length === 0 ? (
            <EmptyState label="source structure maps" />
          ) : (
            maps.map((map) => (
              <div key={map.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{map.sourceType}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{map.documentShape}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{map.mapKind}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{map.status}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatNYDateTime(map.createdAt)}
                  </span>
                </div>
                <p className="mt-2">{map.summary ?? 'No summary'}</p>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
