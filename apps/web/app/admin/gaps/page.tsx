export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { and, asc, count, desc, eq, inArray, isNull, ne, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { gaps, employees, modelCoverageConversions } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { formatNYDate } from '@/lib/time';
import {
  clampModelCoveragePage,
  getModelCoverageConversionDisplay,
  getModelCoverageEligibility,
  MODEL_COVERAGE_PAGE_SIZE,
  parseModelCoveragePage,
} from '@/lib/model-coverage-conversion';
import {
  cancelCoverageConversion,
  createCoverageConversionDraft,
  sendCoverageConversion,
  updateGapStatus,
} from './_actions';

const STATUS_TABS = [
  { label: 'Open', value: 'open' },
  { label: 'Queued', value: 'queued' },
  { label: 'Asked', value: 'asked' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'All', value: 'all' },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    open: 'bg-yellow-100 text-yellow-800',
    queued: 'bg-blue-100 text-blue-700',
    asked: 'bg-purple-100 text-purple-800',
    resolved: 'bg-green-100 text-green-800',
    stale: 'bg-gray-100 text-gray-600',
    rejected: 'bg-red-100 text-red-800',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

function priorityBadge(priority: string) {
  const map: Record<string, string> = {
    low: 'bg-gray-100 text-gray-600',
    medium: 'bg-blue-100 text-blue-700',
    high: 'bg-orange-100 text-orange-800',
    urgent: 'bg-red-100 text-red-800',
  };
  return map[priority] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminGapsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; coveragePage?: string }>;
}) {
  const { status, coveragePage } = await searchParams;
  const activeStatus = status ?? 'open';

  const db = getDirectDb();
  const coverageCountRows = await db
    .select({ value: count() })
    .from(gaps)
    .where(eq(gaps.gapType, 'model_coverage'));
  const coverageFindingCount = coverageCountRows[0]?.value ?? 0;
  const activeCoveragePage = clampModelCoveragePage(
    parseModelCoveragePage(coveragePage),
    coverageFindingCount,
  );
  const coveragePageCount = Math.max(
    1,
    Math.ceil(coverageFindingCount / MODEL_COVERAGE_PAGE_SIZE),
  );

  const activeEmployees = await db
    .select({ id: employees.id, name: employees.name, role: employees.role })
    .from(employees)
    .where(isNull(employees.disabledAt))
    .orderBy(employees.name);

  const coverageFindings = await db
    .select({
      id: gaps.id,
      questionToAsk: gaps.questionToAsk,
      whyItMatters: gaps.whyItMatters,
      status: gaps.status,
      sourceContext: gaps.sourceContext,
      conversionId: modelCoverageConversions.id,
      conversionStatus: modelCoverageConversions.status,
      conversionQuestion: modelCoverageConversions.questionToAsk,
      conversionReason: modelCoverageConversions.conversionReason,
      targetEmployeeIds: modelCoverageConversions.targetEmployeeIds,
      createdGapIds: modelCoverageConversions.createdGapIds,
    })
    .from(gaps)
    .leftJoin(
      modelCoverageConversions,
      and(
        eq(modelCoverageConversions.sourceGapId, gaps.id),
        inArray(modelCoverageConversions.status, ['draft', 'sent']),
      ),
    )
    .where(eq(gaps.gapType, 'model_coverage'))
    .orderBy(
      asc(sql`CASE
        WHEN ${modelCoverageConversions.status} = 'draft' THEN 0
        WHEN ${modelCoverageConversions.status} = 'sent' THEN 1
        WHEN ${gaps.status} = 'open'
          AND jsonb_typeof(${gaps.sourceContext}->'sourceType') = 'string'
          AND btrim(${gaps.sourceContext}->>'sourceType') <> ''
          AND jsonb_typeof(${gaps.sourceContext}->'sourceId') = 'string'
          AND btrim(${gaps.sourceContext}->>'sourceId') <> ''
          AND jsonb_typeof(${gaps.sourceContext}->'mapId') = 'string'
          AND btrim(${gaps.sourceContext}->>'mapId') <> ''
          AND jsonb_typeof(${gaps.sourceContext}->'mapElementRef') = 'string'
          AND btrim(${gaps.sourceContext}->>'mapElementRef') <> ''
          AND jsonb_typeof(${gaps.sourceContext}->'mapElementKind') = 'string'
          AND btrim(${gaps.sourceContext}->>'mapElementKind') <> ''
          AND jsonb_typeof(${gaps.sourceContext}->'mapShape') = 'string'
          AND btrim(${gaps.sourceContext}->>'mapShape') <> ''
          AND jsonb_typeof(${gaps.sourceContext}->'mapElementLocalId') = 'string'
          AND btrim(${gaps.sourceContext}->>'mapElementLocalId') <> ''
        THEN 2
        ELSE 3
      END`),
      desc(gaps.createdAt),
      desc(gaps.id),
    )
    .limit(MODEL_COVERAGE_PAGE_SIZE)
    .offset((activeCoveragePage - 1) * MODEL_COVERAGE_PAGE_SIZE);

  const rows = await db
    .select({
      id: gaps.id,
      gapType: gaps.gapType,
      questionToAsk: gaps.questionToAsk,
      whyItMatters: gaps.whyItMatters,
      priority: gaps.priority,
      status: gaps.status,
      targetDepartment: gaps.targetDepartment,
      createdAt: gaps.createdAt,
      employeeName: employees.name,
    })
    .from(gaps)
    .leftJoin(employees, eq(employees.id, gaps.targetEmployeeId))
    .where(
      and(
        ne(gaps.gapType, 'model_coverage'),
        activeStatus !== 'all'
          ? eq(gaps.status, activeStatus as 'open' | 'queued' | 'asked' | 'resolved' | 'stale' | 'rejected')
          : undefined,
      ),
    )
    .orderBy(desc(gaps.createdAt));

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Gaps</h1>
        <p className="text-sm text-muted-foreground">
          Questions the Oracle wants to ask employees to fill knowledge gaps. Resolving a gap
          here marks it as addressed without waiting for an Oracle interjection.
        </p>
      </header>

      <div className="flex gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === activeStatus;
          return (
            <Link
              key={tab.value}
              href={`/admin/gaps?status=${tab.value}&coveragePage=${activeCoveragePage}`}
              className={`rounded px-3 py-1 ${
                isActive
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Model coverage findings ({coverageFindingCount})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {coverageFindings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No model coverage findings.</p>
          ) : coverageFindings.map((finding) => {
            const source = finding.sourceContext as Record<string, string> | null;
            const targetIds = Array.isArray(finding.targetEmployeeIds)
              ? finding.targetEmployeeIds as string[]
              : [];
            const eligibility = getModelCoverageEligibility({
              gapType: 'model_coverage',
              status: finding.status,
              sourceContext: finding.sourceContext,
            });
            const conversionDisplay = getModelCoverageConversionDisplay(
              finding.conversionStatus,
              eligibility.eligible,
            );
            return (
              <div key={finding.id} className="rounded border p-4 text-sm">
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span>{finding.status}</span>
                  <span>{source?.mapElementKind ?? 'unknown element'}: {source?.mapElementRef ?? 'missing source details'}</span>
                </div>
                <p className="mt-2">{finding.questionToAsk}</p>
                {finding.conversionId ? (
                  <div className="mt-4 rounded bg-muted p-3">
                    <p className="font-medium">Conversion {finding.conversionStatus}</p>
                    <p className="mt-1">{finding.conversionQuestion}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{finding.conversionReason}</p>
                    <p className="mt-1 text-xs">{targetIds.length} recipient{targetIds.length === 1 ? '' : 's'}</p>
                    {conversionDisplay.showBlockedSendReason ? (
                      <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-amber-900">
                        {eligibility.eligible ? null : eligibility.reason} Sending is unavailable.
                      </p>
                    ) : null}
                    {conversionDisplay.showSend || conversionDisplay.showCancel ? (
                      <div className="mt-3 flex gap-2">
                        {conversionDisplay.showSend ? (
                          <form action={sendCoverageConversion}>
                            <input type="hidden" name="conversionId" value={finding.conversionId} />
                            <Button type="submit" size="sm">Send questions</Button>
                          </form>
                        ) : null}
                        {conversionDisplay.showCancel ? (
                          <form action={cancelCoverageConversion}>
                            <input type="hidden" name="conversionId" value={finding.conversionId} />
                            <Button type="submit" size="sm" variant="outline">Cancel draft</Button>
                          </form>
                        ) : null}
                      </div>
                    ) : null}
                    {conversionDisplay.showSentResult ? (
                      <p className="mt-2 text-xs">{Array.isArray(finding.createdGapIds) ? finding.createdGapIds.length : 0} employee gap(s) created.</p>
                    ) : null}
                  </div>
                ) : !eligibility.eligible ? (
                  <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-amber-900">
                    {eligibility.reason}
                  </div>
                ) : (
                  <form action={createCoverageConversionDraft} className="mt-4 grid gap-3 md:grid-cols-2">
                    <input type="hidden" name="sourceGapId" value={finding.id} />
                    <input type="hidden" name="returnStatus" value={activeStatus} />
                    <label className="text-xs font-medium">
                      Employee-facing question
                      <textarea name="questionToAsk" required rows={3} className="mt-1 w-full rounded border bg-background p-2 font-normal" />
                    </label>
                    <label className="text-xs font-medium">
                      Why should a person answer this?
                      <textarea name="conversionReason" required rows={3} className="mt-1 w-full rounded border bg-background p-2 font-normal" />
                    </label>
                    <label className="text-xs font-medium md:col-span-2">
                      Recipients
                      <select name="targetEmployeeIds" required multiple size={5} className="mt-1 w-full rounded border bg-background p-2 font-normal">
                        {activeEmployees.map((employee) => (
                          <option key={employee.id} value={employee.id}>{employee.name} - {employee.role}</option>
                        ))}
                      </select>
                    </label>
                    <Button type="submit" size="sm" className="w-fit">Save draft</Button>
                  </form>
                )}
              </div>
            );
          })}
          {coveragePageCount > 1 ? (
            <nav
              className="flex items-center justify-between border-t pt-4 text-sm"
              aria-label="Model coverage finding pages"
            >
              <span className="text-muted-foreground">
                Page {activeCoveragePage} of {coveragePageCount}
              </span>
              <div className="flex gap-2">
                {activeCoveragePage > 1 ? (
                  <Link
                    className="rounded border px-3 py-1 hover:bg-muted"
                    href={`/admin/gaps?status=${activeStatus}&coveragePage=${activeCoveragePage - 1}`}
                  >
                    Previous
                  </Link>
                ) : null}
                {activeCoveragePage < coveragePageCount ? (
                  <Link
                    className="rounded border px-3 py-1 hover:bg-muted"
                    href={`/admin/gaps?status=${activeStatus}&coveragePage=${activeCoveragePage + 1}`}
                  >
                    Next
                  </Link>
                ) : null}
              </div>
            </nav>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} gaps</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No gaps yet. The contradiction-watcher worker will identify gaps once claims
              are extracted and approved.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Question</th>
                    <th className="py-2 pr-4">Why it matters</th>
                    <th className="py-2 pr-4">Priority</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Target</th>
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-3 pr-4 max-w-xs">
                        <span className="line-clamp-3">{row.questionToAsk}</span>
                      </td>
                      <td className="py-3 pr-4 max-w-xs text-xs text-muted-foreground">
                        <span className="line-clamp-2">{row.whyItMatters}</span>
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium ${priorityBadge(row.priority)}`}
                        >
                          {row.priority}
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.status)}`}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs">
                        {row.employeeName ?? row.targetDepartment ?? '—'}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                        {formatNYDate(row.createdAt)}
                      </td>
                      <td className="py-3">
                        {['open', 'queued', 'asked'].includes(row.status) && (
                          <div className="flex gap-1">
                            <form action={updateGapStatus}>
                              <input type="hidden" name="id" value={row.id} />
                              <input type="hidden" name="status" value="resolved" />
                              <button
                                type="submit"
                                className="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                              >
                                Resolve
                              </button>
                            </form>
                            <form action={updateGapStatus}>
                              <input type="hidden" name="id" value={row.id} />
                              <input type="hidden" name="status" value="stale" />
                              <button
                                type="submit"
                                className="rounded bg-gray-400 px-2 py-1 text-xs text-white hover:bg-gray-500"
                              >
                                Stale
                              </button>
                            </form>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
