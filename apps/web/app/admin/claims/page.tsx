export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDate } from '@/lib/time';
import { AssignQuestionForm } from './_components/assign-question-form';
import { BulkEvaluateBar } from './_components/bulk-evaluate-bar';
import { reviseClaim, updateClaimStatus, translateClaimsForChina } from './_actions';

type ClaimRow = {
  id: string;
  summary: string;
  claim_type: string;
  status: string;
  impact_score: number;
  confidence_score: number;
  created_at: string;
  exact_quote: string | null;
  source_type: string | null;
  employee_name: string | null;
  domain_ids: string[] | null;
  domain_names: string[] | null;
  revision_reviewer_id: string | null;
  revision_reviewer_name: string | null;
  // China bilingual layer (china_imp.md): languages this claim is translated into
  // — the persisted "routed to which group" signal; null when none.
  translated_langs: string[] | null;
  // Names of employees this claim has been sent to for review (open/queued/asked
  // claim_review_question gaps). Persisted signal of "who is evaluating this";
  // null when the claim hasn't been sent to anyone.
  review_assignees: string[] | null;
};

type EmployeeOption = {
  id: string;
  name: string;
  role: string;
};

type GroupOption = {
  id: string;
  name: string;
  memberCount: number;
};

const STATUS_TABS = [
  { label: 'Pending review', value: 'pending_review' },
  { label: 'Approved', value: 'approved' },
  { label: 'Rejected', value: 'rejected' },
  { label: 'All', value: 'all' },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending_review: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    superseded: 'bg-gray-100 text-gray-600',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminClaimsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'pending_review';

  const db = getDirectDb();

  const whereClause =
    activeStatus !== 'all' ? sql`WHERE c.status = ${activeStatus}` : sql``;

  const result = await db.execute(sql`
    SELECT
      c.id,
      c.summary,
      c.claim_type,
      c.status,
      c.impact_score,
      c.confidence_score,
      c.created_at,
      ce.exact_quote,
      ce.source_type,
      e.name AS employee_name,
      COALESCE(d.domain_ids, ARRAY[]::text[]) AS domain_ids,
      COALESCE(d.domain_names, ARRAY[]::text[]) AS domain_names,
      rev.reviewed_by_employee_id AS revision_reviewer_id,
      rev.reviewer_name AS revision_reviewer_name,
      (
        SELECT jsonb_agg(ct.lang ORDER BY ct.lang)
        FROM claim_translations ct
        WHERE ct.claim_id = c.id
      ) AS translated_langs,
      (
        SELECT jsonb_agg(DISTINCT te.name)
        FROM gaps g
        JOIN employees te ON te.id = g.target_employee_id
        WHERE g.gap_type = 'claim_review_question'
          AND g.status IN ('open', 'queued', 'asked')
          AND g.related_claim_ids ? c.id::text
      ) AS review_assignees
    FROM claims c
    LEFT JOIN LATERAL (
      SELECT exact_quote, source_type, asserted_by_employee_id
      FROM claim_evidence
      WHERE claim_id = c.id
      ORDER BY confidence DESC NULLS LAST, created_at ASC
      LIMIT 1
    ) ce ON true
    LEFT JOIN employees e ON e.id = ce.asserted_by_employee_id
    LEFT JOIN LATERAL (
      SELECT
        array_agg(ktd.id ORDER BY ktd.display_order, ktd.name) AS domain_ids,
        array_agg(ktd.name ORDER BY ktd.display_order, ktd.name) AS domain_names
      FROM claim_top_domains ctd
      JOIN knowledge_top_domains ktd ON ktd.id = ctd.top_domain_id
      WHERE ctd.claim_id = c.id
    ) d ON true
    LEFT JOIN LATERAL (
      SELECT cre.reviewed_by_employee_id, reviewer.name AS reviewer_name
      FROM claim_review_events cre
      LEFT JOIN employees reviewer ON reviewer.id = cre.reviewed_by_employee_id
      WHERE cre.replacement_claim_id = c.id
        AND cre.action = 'revise'
      ORDER BY cre.created_at DESC
      LIMIT 1
    ) rev ON true
    ${whereClause}
    ORDER BY c.created_at DESC
  `);
  const employeesResult = await db.execute(sql`
    SELECT id, name, role
    FROM employees
    WHERE disabled_at IS NULL
    ORDER BY name
  `);
  const groupsResult = await db.execute(sql`
    SELECT
      crg.id,
      crg.name,
      COUNT(e.id)::int AS "memberCount"
    FROM claim_review_groups crg
    LEFT JOIN claim_review_group_members crgm ON crgm.group_id = crg.id
    LEFT JOIN employees e ON e.id = crgm.employee_id AND e.disabled_at IS NULL
    WHERE crg.archived_at IS NULL
    GROUP BY crg.id, crg.name
    ORDER BY crg.name
  `);

  const rows = [...result] as unknown as ClaimRow[];
  const employeeOptions = [...employeesResult] as unknown as EmployeeOption[];
  const groupOptions = [...groupsResult] as unknown as GroupOption[];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Claims</h1>
        <p className="text-sm text-muted-foreground">
          Review extracted claims. Approving a claim makes it eligible for brain section
          synthesis.
        </p>
      </header>

      <div className="flex gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === activeStatus;
          return (
            <Link
              key={tab.value}
              href={`/admin/claims?status=${tab.value}`}
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

      {/* Bulk "ask selected to evaluate": tick pending claims, choose recipients,
          and route each claim to them for evaluation (the China translation, if
          any recipient is zh-CN, happens automatically server-side). Lives
          outside the table so per-row forms aren't nested; pending-row checkboxes
          associate via form="bulk-evaluate". */}
      <BulkEvaluateBar employees={employeeOptions} groups={groupOptions} />

      {/* China bilingual layer (china_imp.md): bulk-translate the ticked approved
          claims for the China team. Lives outside the table so per-row forms
          aren't nested; row checkboxes associate via form="translate-claims". */}
      <form
        id="translate-claims"
        action={translateClaimsForChina}
        className="flex flex-wrap items-center gap-3 rounded border border-dashed p-3 text-sm"
      >
        <button
          type="submit"
          className="rounded bg-foreground px-3 py-1 text-xs text-background hover:opacity-90"
        >
          Translate selected for China team
        </button>
        <span className="text-xs text-muted-foreground">
          Tick approved claims, then submit. A green ✓ badge marks claims already
          translated (and to which language) — persists across refreshes.
          Untranslated claims are still visible to the China team, in English. To
          ask people to verify a claim, use “Assign question” in the Actions column.
        </span>
      </form>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} claims</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No claims yet. Workers will populate this table once messages have been
              processed by the extraction worker.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4" title="Tick pending claims to ask someone to evaluate, or approved claims to translate for the China team">
                      ☑
                    </th>
                    <th className="py-2 pr-4">Summary</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Domains</th>
                    <th className="py-2 pr-4">Impact</th>
                    <th className="py-2 pr-4">Confidence</th>
                    <th className="py-2 pr-4">Employee</th>
                    <th className="py-2 pr-4">Evidence</th>
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const wasCorrected = row.revision_reviewer_id !== null;
                    return (
                    <tr
                      key={row.id}
                      className={`border-b last:border-0 ${
                        wasCorrected ? 'border-l-4 border-l-sky-500 bg-sky-50/60' : ''
                      }`}
                    >
                      <td className="py-3 pr-4 align-top">
                        <div className="flex flex-col items-center gap-1">
                          {row.status === 'approved' ? (
                            <input
                              type="checkbox"
                              name="claimId"
                              value={row.id}
                              form="translate-claims"
                              aria-label="Select this claim to translate for the China team"
                            />
                          ) : row.status === 'pending_review' ? (
                            <input
                              type="checkbox"
                              name="claimId"
                              value={row.id}
                              form="bulk-evaluate"
                              aria-label="Select this pending claim to ask someone to evaluate"
                            />
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                          {row.translated_langs && row.translated_langs.length > 0 && (
                            <div className="flex flex-wrap justify-center gap-0.5">
                              {row.translated_langs.map((lang) => (
                                <span
                                  key={lang}
                                  title={`Translated — visible to ${lang} readers in their language`}
                                  className="rounded bg-green-100 px-1 py-0.5 text-[10px] font-medium text-green-800"
                                >
                                  ✓ {lang}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="max-w-[28rem] whitespace-pre-wrap py-3 pr-4 align-top">
                        {wasCorrected && (
                          <div className="mb-2">
                            <span className="rounded bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800">
                              Corrected by {row.revision_reviewer_name ?? 'reviewer'}
                            </span>
                          </div>
                        )}
                        {row.review_assignees && row.review_assignees.length > 0 && (
                          <div className="mb-2 flex flex-wrap items-center gap-1">
                            <span
                              className="rounded bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800"
                              title={`Out for review — awaiting input from ${row.review_assignees.join(', ')}`}
                            >
                              🔁 Sent to review
                            </span>
                            {[...row.review_assignees].sort((a, b) => a.localeCompare(b)).map((name) => (
                              <span
                                key={`${row.id}-rev-${name}`}
                                className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700"
                              >
                                {name}
                              </span>
                            ))}
                          </div>
                        )}
                        {row.summary}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                        {row.claim_type}
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.status)}`}
                        >
                          {row.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-3 pr-4 max-w-[14rem]">
                        {row.domain_names && row.domain_names.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {row.domain_names.map((name, i) => (
                              <span
                                key={`${row.id}-${row.domain_ids?.[i] ?? name}`}
                                className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                                title={row.domain_ids?.[i] ?? name}
                              >
                                {name}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-center">{row.impact_score}</td>
                      <td className="py-3 pr-4 text-center">{row.confidence_score}</td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        {row.employee_name ?? '—'}
                      </td>
                      <td className="max-w-[34rem] whitespace-pre-wrap py-3 pr-4 align-top text-xs text-muted-foreground">
                        {row.exact_quote ? (
                          <span className="italic">
                            &ldquo;{row.exact_quote}&rdquo;
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                        {formatNYDate(row.created_at)}
                      </td>
                      <td className="py-3">
                        {['pending_review', 'approved'].includes(row.status) && (
                          <div className="flex min-w-[18rem] flex-col gap-2">
                            {row.status === 'pending_review' && (
                              <div className="flex gap-2">
                              <form action={updateClaimStatus}>
                                <input type="hidden" name="id" value={row.id} />
                                <input type="hidden" name="status" value="approved" />
                                <button
                                  type="submit"
                                  className="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                                >
                                  Approve
                                </button>
                              </form>
                              <form action={updateClaimStatus}>
                                <input type="hidden" name="id" value={row.id} />
                                <input type="hidden" name="status" value="rejected" />
                                <button
                                  type="submit"
                                  className="rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700"
                                >
                                  Reject
                                </button>
                              </form>
                              </div>
                            )}
                            <details className="rounded border bg-background p-2">
                              <summary className="cursor-pointer text-xs font-medium">
                                {row.status === 'approved' ? 'Edit approved claim' : 'Revise'}
                              </summary>
                              <form action={reviseClaim} className="mt-2 space-y-2">
                                <input type="hidden" name="id" value={row.id} />
                                <label className="block text-[11px] font-medium text-muted-foreground">
                                  Claim type
                                  <input
                                    name="claimType"
                                    defaultValue={row.claim_type}
                                    className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
                                  />
                                </label>
                                <label className="block text-[11px] font-medium text-muted-foreground">
                                  {row.status === 'approved' ? 'Updated summary' : 'Corrected summary'}
                                  <textarea
                                    name="summary"
                                    defaultValue={row.summary}
                                    rows={3}
                                    className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
                                  />
                                </label>
                                <div className="grid grid-cols-2 gap-2">
                                  <label className="block text-[11px] font-medium text-muted-foreground">
                                    Impact
                                    <input
                                      name="impactScore"
                                      type="number"
                                      min="1"
                                      max="10"
                                      defaultValue={row.impact_score}
                                      className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
                                    />
                                  </label>
                                  <label className="block text-[11px] font-medium text-muted-foreground">
                                    Confidence
                                    <input
                                      name="confidenceScore"
                                      type="number"
                                      min="1"
                                      max="10"
                                      defaultValue={row.confidence_score}
                                      className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
                                    />
                                  </label>
                                </div>
                                <label className="block text-[11px] font-medium text-muted-foreground">
                                  Reviewer note
                                  <textarea
                                    name="reviewerNote"
                                    rows={2}
                                    placeholder={
                                      row.status === 'approved'
                                        ? 'Why is this approved claim changing?'
                                        : 'What did the AI get wrong?'
                                    }
                                    className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
                                  />
                                </label>
                                <button
                                  type="submit"
                                  className="rounded bg-foreground px-2 py-1 text-xs text-background hover:bg-foreground/90"
                                >
                                  {row.status === 'approved'
                                    ? 'Create replacement for review'
                                    : 'Save revised claim'}
                                </button>
                              </form>
                            </details>
                            {row.status === 'pending_review' && (
                              <details className="rounded border bg-background p-2">
                                <summary className="cursor-pointer text-xs font-medium">
                                  Ask someone
                                </summary>
                                <AssignQuestionForm
                                  claimId={row.id}
                                  claimSummary={row.summary}
                                  employees={employeeOptions}
                                  groups={groupOptions}
                                />
                              </details>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
