import { desc, eq, inArray, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  macroRelationshipClaims,
  macroRelationships,
  sourceCoverageFindings,
  sourceOutlines,
  claims,
} from '@oracle/db/schema';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';
import {
  convertCoverageFindingToGap,
  createManualMacroRelationship,
  dismissCoverageFinding,
  dropMacroSupportAndRevalidate,
  runCoverageAudit,
  runMacroRelationshipExtraction,
  sweepMacroStaleness,
  updateMacroRelationshipStatus,
} from './_actions';

export const dynamic = 'force-dynamic';

export default async function AdminMacroPage() {
  const db = getDirectDb();
  const relationships = await db
    .select({
      id: macroRelationships.id,
      relationshipType: macroRelationships.relationshipType,
      summary: macroRelationships.summary,
      status: macroRelationships.status,
      confidenceScore: macroRelationships.confidenceScore,
      impactScore: macroRelationships.impactScore,
      triageScore: macroRelationships.triageScore,
      sourceDensity: sql<number>`(
        SELECT COUNT(DISTINCT concat_ws(':', mrs.source_type, mrs.document_id::text, mrs.channel_id::text, mrs.meeting_transcript_id::text))
        FROM macro_relationship_sources mrs
        WHERE mrs.macro_relationship_id = ${macroRelationships.id}
      )`,
      stalenessReason: macroRelationships.stalenessReason,
      sourceOutlineId: macroRelationships.sourceOutlineId,
      createdAt: macroRelationships.createdAt,
    })
    .from(macroRelationships)
    .orderBy(
      sql`CASE ${macroRelationships.status}
        WHEN 'pending_review' THEN 0
        WHEN 'needs_review' THEN 1
        WHEN 'blocked_pending_support' THEN 2
        WHEN 'stale_support' THEN 3
        ELSE 4
      END`,
      sql`COALESCE(${macroRelationships.triageScore}, 0) DESC`,
      desc(macroRelationships.impactScore),
      sql`(
        SELECT COUNT(DISTINCT concat_ws(':', mrs.source_type, mrs.document_id::text, mrs.channel_id::text, mrs.meeting_transcript_id::text))
        FROM macro_relationship_sources mrs
        WHERE mrs.macro_relationship_id = ${macroRelationships.id}
      ) DESC`,
      desc(macroRelationships.createdAt),
    )
    .limit(100);

  const supportRows =
    relationships.length > 0
      ? await db
          .select({
            relationshipId: macroRelationshipClaims.macroRelationshipId,
            claimId: claims.id,
            supportRole: macroRelationshipClaims.supportRole,
            status: claims.status,
            summary: claims.summary,
          })
          .from(macroRelationshipClaims)
          .innerJoin(claims, eq(claims.id, macroRelationshipClaims.claimId))
          .where(inArray(macroRelationshipClaims.macroRelationshipId, relationships.map((row) => row.id)))
      : [];
  const supportByRelationship = new Map<string, typeof supportRows>();
  for (const row of supportRows) {
    const list = supportByRelationship.get(row.relationshipId) ?? [];
    list.push(row);
    supportByRelationship.set(row.relationshipId, list);
  }

  const findings = await db
    .select({
      id: sourceCoverageFindings.id,
      sourceOutlineId: sourceCoverageFindings.sourceOutlineId,
      findingType: sourceCoverageFindings.findingType,
      summary: sourceCoverageFindings.summary,
      suggestedQuestion: sourceCoverageFindings.suggestedQuestion,
      severity: sourceCoverageFindings.severity,
      status: sourceCoverageFindings.status,
      createdAt: sourceCoverageFindings.createdAt,
    })
    .from(sourceCoverageFindings)
    .orderBy(desc(sourceCoverageFindings.createdAt))
    .limit(100);

  const outlines = await db
    .select({
      id: sourceOutlines.id,
      summary: sourceOutlines.summary,
      status: sourceOutlines.status,
      createdAt: sourceOutlines.createdAt,
    })
    .from(sourceOutlines)
    .orderBy(desc(sourceOutlines.createdAt))
    .limit(50);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Macro</h1>
        <p className="text-sm text-muted-foreground">
          Review macro relationships and source coverage findings. Approved relationships are served only when every support claim is still approved.
        </p>
      </header>

      <div className="flex flex-wrap gap-3">
        <form action={sweepMacroStaleness}>
          <Button type="submit" variant="outline">Sweep stale support</Button>
        </form>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Manual relationship</CardTitle>
          <CardDescription>Create a reviewable macro relationship from approved support claim IDs.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={createManualMacroRelationship} className="grid gap-3 text-sm md:grid-cols-[12rem_1fr_auto]">
            <select name="relationshipType" className="rounded border bg-background px-2 py-1">
              <option value="dependency">Dependency</option>
              <option value="handoff">Handoff</option>
              <option value="sequence">Sequence</option>
              <option value="exception_path">Exception path</option>
              <option value="policy_vs_practice_tension">Policy vs practice tension</option>
              <option value="workaround_to_system_limitation">Workaround to system limitation</option>
              <option value="definition_resolution">Definition resolution</option>
            </select>
            <input name="summary" placeholder="Relationship summary" className="rounded border bg-background px-2 py-1" />
            <Button type="submit">Create</Button>
            <textarea
              name="claimIds"
              placeholder="Support claim IDs, separated by commas or spaces"
              rows={2}
              className="rounded border bg-background px-2 py-1 md:col-span-3"
            />
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Source outlines</CardTitle>
          <CardDescription>Run coverage audits against provisional outlines.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {outlines.map((outline) => (
              <div key={outline.id} className="flex items-start justify-between gap-4 rounded border p-3 text-sm">
                <div>
                  <div className="font-medium">{outline.summary ?? 'No summary'}</div>
                  <div className="text-xs text-muted-foreground">
                    {outline.status} · {formatNYDateTime(outline.createdAt)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <form action={runMacroRelationshipExtraction}>
                    <input type="hidden" name="sourceOutlineId" value={outline.id} />
                    <Button size="sm" variant="outline" type="submit">Extract relationships</Button>
                  </form>
                  <form action={runCoverageAudit}>
                    <input type="hidden" name="sourceOutlineId" value={outline.id} />
                    <Button size="sm" variant="outline" type="submit">Audit coverage</Button>
                  </form>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{relationships.length} macro relationships</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {relationships.map((relationship) => {
              const support = supportByRelationship.get(relationship.id) ?? [];
              const canApprove = support.length >= 2 && support.every((row) => row.status === 'approved');
              return (
                <div key={relationship.id} className="rounded border p-4 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">{relationship.relationshipType}</span>
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">{relationship.status}</span>
                    <span className="text-xs text-muted-foreground">
                      triage {relationship.triageScore ?? 'n/a'} · impact {relationship.impactScore} · confidence {relationship.confidenceScore} · sources {relationship.sourceDensity}
                    </span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap">{relationship.summary}</p>
                  {relationship.stalenessReason ? (
                    <p className="mt-2 text-xs text-red-700">{relationship.stalenessReason}</p>
                  ) : null}
                  <div className="mt-3 space-y-2">
                    {support.map((row) => (
                      <label key={`${relationship.id}-${row.claimId}-${row.supportRole}`} className="flex gap-2 text-xs">
                        <input type="checkbox" name="claimId" value={row.claimId} form={`drop-${relationship.id}`} />
                        <span className="min-w-28 text-muted-foreground">{row.supportRole} · {row.status}</span>
                        <span>{row.summary}</span>
                      </label>
                    ))}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <form action={updateMacroRelationshipStatus}>
                      <input type="hidden" name="id" value={relationship.id} />
                      <input type="hidden" name="status" value="approved" />
                      <Button size="sm" type="submit" disabled={!canApprove}>Approve</Button>
                    </form>
                    <form action={updateMacroRelationshipStatus}>
                      <input type="hidden" name="id" value={relationship.id} />
                      <input type="hidden" name="status" value="rejected" />
                      <Button size="sm" variant="outline" type="submit">Reject</Button>
                    </form>
                    <form id={`drop-${relationship.id}`} action={dropMacroSupportAndRevalidate} className="flex gap-2">
                      <input type="hidden" name="id" value={relationship.id} />
                      <Button size="sm" variant="outline" type="submit">Drop selected support</Button>
                    </form>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{findings.length} coverage findings</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {findings.map((finding) => (
              <div key={finding.id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{finding.findingType}</span>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs">{finding.status}</span>
                  <span className="text-xs text-muted-foreground">severity {finding.severity}</span>
                </div>
                <p className="mt-2">{finding.summary}</p>
                {finding.suggestedQuestion ? (
                  <p className="mt-1 text-xs text-muted-foreground">{finding.suggestedQuestion}</p>
                ) : null}
                {finding.status === 'open' ? (
                  <div className="mt-3 flex gap-2">
                    <form action={convertCoverageFindingToGap}>
                      <input type="hidden" name="id" value={finding.id} />
                      <Button size="sm" type="submit">Create gap</Button>
                    </form>
                    <form action={dismissCoverageFinding}>
                      <input type="hidden" name="id" value={finding.id} />
                      <Button size="sm" variant="outline" type="submit">Dismiss</Button>
                    </form>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
