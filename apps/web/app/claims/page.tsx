export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { LogoutButton } from '@/app/_components/logout-button';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AssignQuestionForm } from '@/app/admin/claims/_components/assign-question-form';
import { reviseClaim, updateClaimStatus } from '@/app/admin/claims/_actions';

type ClaimRow = {
  id: string;
  summary: string;
  claim_type: string;
  status: string;
  impact_score: number;
  confidence_score: number;
  created_at: string;
  exact_quote: string | null;
  employee_name: string | null;
  domain_ids: string[] | null;
  domain_names: string[] | null;
  revision_reviewer_id: string | null;
  revision_reviewer_name: string | null;
};

type EmployeeOption = {
  id: string;
  name: string;
  role: string;
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

export default async function ClaimsReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const me = await requireEmployee();
  const { status } = await searchParams;
  const activeStatus = status ?? 'pending_review';
  const db = getDirectDb();

  const statusWhere =
    activeStatus !== 'all' ? sql`AND c.status = ${activeStatus}` : sql``;
  const reviewerWhere = me.isAdmin
    ? sql``
    : sql`
      AND EXISTS (
        SELECT 1
        FROM claim_top_domains ctd_perm
        JOIN knowledge_domain_review_departments kdrd
          ON kdrd.top_domain_id = ctd_perm.top_domain_id
         AND kdrd.can_review_claims = true
        JOIN employee_departments ed
          ON ed.department_id = kdrd.department_id
        WHERE ctd_perm.claim_id = c.id
          AND ed.employee_id = ${me.id}::uuid
      )
    `;

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
      e.name AS employee_name,
      COALESCE(d.domain_ids, ARRAY[]::text[]) AS domain_ids,
      COALESCE(d.domain_names, ARRAY[]::text[]) AS domain_names,
      rev.reviewed_by_employee_id AS revision_reviewer_id,
      rev.reviewer_name AS revision_reviewer_name
    FROM claims c
    LEFT JOIN LATERAL (
      SELECT exact_quote, asserted_by_employee_id
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
    WHERE true
    ${statusWhere}
    ${reviewerWhere}
    ORDER BY c.created_at DESC
  `);
  const employeesResult = await db.execute(sql`
    SELECT id, name, role
    FROM employees
    WHERE disabled_at IS NULL
    ORDER BY name
  `);

  const rows = [...result] as unknown as ClaimRow[];
  const employeeOptions = [...employeesResult] as unknown as EmployeeOption[];

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex items-center justify-between py-4">
          <div className="flex items-center gap-4">
            <Link href="/channels" className="text-lg font-semibold">
              The Oracle
            </Link>
            {me.isAdmin && (
              <Link href="/admin/claims" className="text-sm text-muted-foreground hover:text-foreground">
                Admin claims
              </Link>
            )}
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-muted-foreground">
              {me.name} · {me.role}
            </span>
            <LogoutButton />
          </div>
        </div>
      </header>

      <main className="container space-y-6 py-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold">Claims to review</h1>
          <p className="text-sm text-muted-foreground">
            Domain reviewers can approve, reject, or revise claims for their assigned
            knowledge areas.
          </p>
        </header>

        <div className="flex gap-2 text-sm">
          {STATUS_TABS.map((tab) => {
            const isActive = tab.value === activeStatus;
            return (
              <Link
                key={tab.value}
                href={`/claims?status=${tab.value}`}
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
            <CardTitle className="text-base">{rows.length} claims</CardTitle>
          </CardHeader>
          <CardContent>
            {rows.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No claims are currently assigned to your review domains.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="py-2 pr-4">Summary</th>
                      <th className="py-2 pr-4">Status</th>
                      <th className="py-2 pr-4">Domains</th>
                      <th className="py-2 pr-4">Scores</th>
                      <th className="py-2 pr-4">Evidence</th>
                      <th className="py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const wasCorrected = row.revision_reviewer_id !== null;
                      const correctedByMe = row.revision_reviewer_id === me.id;
                      return (
                      <tr
                        key={row.id}
                        className={`border-b last:border-0 ${
                          wasCorrected ? 'border-l-4 border-l-sky-500 bg-sky-50/60' : ''
                        }`}
                      >
                        <td className="max-w-[28rem] whitespace-pre-wrap py-3 pr-4 align-top">
                          {wasCorrected && (
                            <div className="mb-2">
                              <span className="rounded bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800">
                                {correctedByMe
                                  ? 'Corrected by you'
                                  : `Corrected by ${row.revision_reviewer_name ?? 'reviewer'}`}
                              </span>
                            </div>
                          )}
                          <div className="font-medium">{row.summary}</div>
                          <div className="mt-1 text-xs text-muted-foreground">{row.claim_type}</div>
                        </td>
                        <td className="py-3 pr-4">
                          <span
                            className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.status)}`}
                          >
                            {row.status.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="max-w-[14rem] py-3 pr-4">
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
                        <td className="py-3 pr-4 text-xs text-muted-foreground">
                          Impact {row.impact_score} · Confidence {row.confidence_score}
                        </td>
                        <td className="max-w-[34rem] whitespace-pre-wrap py-3 pr-4 align-top text-xs text-muted-foreground">
                          {row.exact_quote ? (
                            <span className="italic">&ldquo;{row.exact_quote}&rdquo;</span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="py-3">
                          {row.status === 'pending_review' && (
                            <div className="flex min-w-[18rem] flex-col gap-2">
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
                              <details className="rounded border bg-background p-2">
                                <summary className="cursor-pointer text-xs font-medium">Revise</summary>
                                <form action={reviseClaim} className="mt-2 space-y-2">
                                  <input type="hidden" name="id" value={row.id} />
                                  <input
                                    name="claimType"
                                    defaultValue={row.claim_type}
                                    className="w-full rounded border bg-background px-2 py-1 text-xs"
                                  />
                                  <textarea
                                    name="summary"
                                    defaultValue={row.summary}
                                    rows={3}
                                    className="w-full rounded border bg-background px-2 py-1 text-xs"
                                  />
                                  <div className="grid grid-cols-2 gap-2">
                                    <input
                                      name="impactScore"
                                      type="number"
                                      min="1"
                                      max="10"
                                      defaultValue={row.impact_score}
                                      className="rounded border bg-background px-2 py-1 text-xs"
                                    />
                                    <input
                                      name="confidenceScore"
                                      type="number"
                                      min="1"
                                      max="10"
                                      defaultValue={row.confidence_score}
                                      className="rounded border bg-background px-2 py-1 text-xs"
                                    />
                                  </div>
                                  <textarea
                                    name="reviewerNote"
                                    rows={2}
                                    placeholder="What did the AI get wrong?"
                                    className="w-full rounded border bg-background px-2 py-1 text-xs"
                                  />
                                  <button
                                    type="submit"
                                    className="rounded bg-foreground px-2 py-1 text-xs text-background hover:bg-foreground/90"
                                  >
                                    Save revised claim
                                  </button>
                                </form>
                              </details>
                              <details className="rounded border bg-background p-2">
                                <summary className="cursor-pointer text-xs font-medium">Ask someone</summary>
                                <AssignQuestionForm
                                  claimId={row.id}
                                  claimSummary={row.summary}
                                  employees={employeeOptions}
                                  compact
                                />
                              </details>
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
      </main>
    </div>
  );
}
