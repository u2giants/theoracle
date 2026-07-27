import { desc, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  businessModelChanges,
  businessObjects,
  businessObjectVersions,
  sourceWorkflowMaps,
} from '@oracle/db/schema';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

export const dynamic = 'force-dynamic';

async function countRows(
  db: ReturnType<typeof getDirectDb>,
  table:
    | typeof businessObjects
    | typeof businessObjectVersions
    | typeof businessModelChanges
    | typeof sourceWorkflowMaps,
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

  const [objectCount, versionCount, proposalCount, mapCount, objects, versions, proposals, maps] =
    await Promise.all([
      countRows(db, businessObjects),
      countRows(db, businessObjectVersions),
      countRows(db, businessModelChanges),
      countRows(db, sourceWorkflowMaps),
      db
        .select({
          id: businessObjects.id,
          objectKind: businessObjects.objectKind,
          name: businessObjects.name,
          slug: businessObjects.slug,
          status: businessObjects.status,
          summary: businessObjects.summary,
          currentVersionId: businessObjects.currentVersionId,
          updatedAt: businessObjects.updatedAt,
        })
        .from(businessObjects)
        .orderBy(desc(businessObjects.updatedAt))
        .limit(20),
      db
        .select({
          id: businessObjectVersions.id,
          objectId: businessObjectVersions.objectId,
          versionNumber: businessObjectVersions.versionNumber,
          status: businessObjectVersions.status,
          summary: businessObjectVersions.summary,
          approvedAt: businessObjectVersions.approvedAt,
          createdAt: businessObjectVersions.createdAt,
        })
        .from(businessObjectVersions)
        .orderBy(desc(businessObjectVersions.createdAt))
        .limit(20),
      db
        .select({
          id: businessModelChanges.id,
          objectId: businessModelChanges.objectId,
          objectKind: businessModelChanges.objectKind,
          proposedSlug: businessModelChanges.proposedSlug,
          legacyProcessId: businessModelChanges.processId,
          changeType: businessModelChanges.changeType,
          status: businessModelChanges.status,
          summary: businessModelChanges.summary,
          sourceWorkflowMapId: businessModelChanges.sourceWorkflowMapId,
          operations: businessModelChanges.operationsJson,
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
          objects and immutable versions.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
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
            <CardTitle className="text-base">{objectCount}</CardTitle>
            <CardDescription>Business objects</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{versionCount}</CardTitle>
            <CardDescription>Immutable versions</CardDescription>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Business objects</CardTitle>
          <CardDescription>
            Approved versions will become the primary answering context.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {objects.length === 0 ? (
            <EmptyState label="business objects" />
          ) : (
            objects.map((object) => (
              <div key={object.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{object.name}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{object.objectKind}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{object.status}</span>
                  <span className="text-xs text-muted-foreground">
                    updated {formatNYDateTime(object.updatedAt)}
                  </span>
                </div>
                <p className="mt-2 font-mono text-xs text-muted-foreground">{object.slug}</p>
                {object.summary ? (
                  <p className="mt-2 text-muted-foreground">{object.summary}</p>
                ) : null}
                {object.currentVersionId ? (
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    current version {object.currentVersionId}
                  </p>
                ) : null}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Immutable versions</CardTitle>
          <CardDescription>
            Each approved change creates a new version instead of overwriting prior knowledge.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {versions.length === 0 ? (
            <EmptyState label="business object versions" />
          ) : (
            versions.map((version) => (
              <div key={version.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Version {version.versionNumber}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{version.status}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatNYDateTime(version.approvedAt ?? version.createdAt)}
                  </span>
                </div>
                <p className="mt-2">{version.summary ?? 'No summary'}</p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  object {version.objectId}
                </p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model-change proposals</CardTitle>
          <CardDescription>R2 through R5 will populate this queue in shadow mode.</CardDescription>
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
                  {proposal.objectId
                    ? `object ${proposal.objectId}`
                    : proposal.proposedSlug
                      ? `new ${proposal.objectKind}/${proposal.proposedSlug}`
                      : `legacy process ${proposal.legacyProcessId ?? 'none'}`}
                </p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  map {proposal.sourceWorkflowMapId}
                </p>
                {(() => {
                  const details = proposal.operations as {
                    shadow?: boolean;
                    applyEligible?: boolean;
                    operations?: Array<{ type?: string; sourceElementRef?: string }>;
                    evidence?: Array<{ claimId?: string; quote?: string }>;
                  };
                  return details.shadow ? (
                    <div className="mt-3 space-y-2 rounded border border-dashed p-3">
                      <p className="font-medium">Shadow proposal. Read only.</p>
                      <p className="text-xs text-muted-foreground">
                        Apply eligible: {details.applyEligible === true ? 'yes' : 'no'}
                      </p>
                      {(details.operations ?? []).map((operation, index) => (
                        <p key={`${operation.sourceElementRef}-${index}`} className="text-xs">
                          {operation.type}: {operation.sourceElementRef}
                        </p>
                      ))}
                      {(details.evidence ?? []).map((evidence, index) => (
                        <blockquote
                          key={`${evidence.claimId}-${index}`}
                          className="border-l-2 pl-3 text-xs text-muted-foreground"
                        >
                          “{evidence.quote}” · claim {evidence.claimId}
                        </blockquote>
                      ))}
                    </div>
                  ) : null;
                })()}
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
