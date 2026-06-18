export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  updateClaimStatus,
  translateClaimsForChina,
  requestClaimVerification,
} from './_actions';

type ClaimRow = {
  id: string;
  summary: string;
  claim_type: string;
  status: string;
  source_lang: string;
  impact_score: number;
  confidence_score: number;
  created_at: string;
  exact_quote: string | null;
  source_type: string | null;
  employee_name: string | null;
  // Languages this claim has already been translated into (china_imp.md). null
  // when none — the persisted "which claims did I route, and to whom" signal.
  translated_langs: string[] | null;
  // True when an open recertification gap references this claim — the persisted
  // "I already asked someone to verify this" signal.
  recert_pending: boolean;
};

type TargetEmployee = { id: string; name: string };
type TargetDepartment = { id: string; display_label: string };

// Locale → short team-facing label for the "Routed" badge.
const LOCALE_LABEL: Record<string, string> = {
  'zh-CN': 'China team (中文)',
  en: 'English',
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
      c.source_lang,
      c.impact_score,
      c.confidence_score,
      c.created_at,
      ce.exact_quote,
      ce.source_type,
      e.name AS employee_name,
      (
        SELECT jsonb_agg(ct.lang ORDER BY ct.lang)
        FROM claim_translations ct
        WHERE ct.claim_id = c.id
      ) AS translated_langs,
      EXISTS (
        SELECT 1 FROM gaps g
        WHERE g.gap_type = 'claim_recertification'
          AND g.status IN ('open', 'queued', 'asked')
          AND g.related_claim_ids @> to_jsonb(c.id::text)
      ) AS recert_pending
    FROM claims c
    LEFT JOIN LATERAL (
      SELECT exact_quote, source_type, asserted_by_employee_id
      FROM claim_evidence
      WHERE claim_id = c.id
      ORDER BY confidence DESC NULLS LAST, created_at ASC
      LIMIT 1
    ) ce ON true
    LEFT JOIN employees e ON e.id = ce.asserted_by_employee_id
    ${whereClause}
    ORDER BY c.created_at DESC
  `);

  const rows = [...result] as unknown as ClaimRow[];

  // Target options for the "ask to verify" picker: the China-team locale group,
  // department "groups", and individual active employees. All are resolved to
  // concrete recipient employees by the worker, so department targeting is safe
  // here (membership comes from the employee_departments junction, not free-text).
  const employeesResult = await db.execute(sql`
    SELECT id, name FROM employees WHERE disabled_at IS NULL ORDER BY name
  `);
  const targetEmployees = [...employeesResult] as unknown as TargetEmployee[];
  const departmentsResult = await db.execute(sql`
    SELECT id, display_label FROM departments ORDER BY display_label
  `);
  const targetDepartments = [...departmentsResult] as unknown as TargetDepartment[];

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

      {/* Bulk actions for the ticked claims (china_imp.md). The form lives
          outside the table so per-row Approve/Reject forms aren't nested inside
          it; row checkboxes associate via the HTML form="bulk-claims" attribute.
          Two submit buttons drive two actions via formAction — translate, or ask
          someone to verify. */}
      <form
        id="bulk-claims"
        className="flex flex-wrap items-center gap-3 rounded border border-dashed p-3 text-sm"
      >
        <button
          type="submit"
          formAction={translateClaimsForChina}
          className="rounded bg-foreground px-3 py-1 text-xs text-background hover:opacity-90"
        >
          Translate selected for China team
        </button>

        <span className="text-muted-foreground">·</span>

        <label className="flex items-start gap-1">
          Ask
          <select
            name="target"
            multiple
            size={5}
            className="min-w-48 rounded border bg-background px-1 py-0.5 text-xs"
          >
            <optgroup label="Groups">
              <option value="locale:zh-CN">China team (zh-CN)</option>
              {targetDepartments.map((d) => (
                <option key={d.id} value={`department:${d.id}`}>
                  {d.display_label}
                </option>
              ))}
            </optgroup>
            <optgroup label="People">
              {targetEmployees.map((e) => (
                <option key={e.id} value={`employee:${e.id}`}>
                  {e.name}
                </option>
              ))}
            </optgroup>
          </select>
          to verify
        </label>
        <button
          type="submit"
          formAction={requestClaimVerification}
          className="rounded border border-foreground px-3 py-1 text-xs hover:bg-muted"
        >
          Ask selected to verify
        </button>

        <span className="w-full text-xs text-muted-foreground">
          Tick approved claims, then choose an action. For verify, pick one or more
          targets (Ctrl/Cmd-click for multiple) — the China team, departments, or
          individuals. Each recipient is asked in their own language, so the
          question is translated to Chinese only for China-team members. A green ✓
          badge marks translated claims; a 🔁 badge marks pending verification asks.
          Both persist across refreshes.
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
                    <th className="py-2 pr-4" title="Select approved claims for a bulk action (translate / ask to verify)">
                      Select
                    </th>
                    <th className="py-2 pr-4">Summary</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Impact</th>
                    <th className="py-2 pr-4">Confidence</th>
                    <th className="py-2 pr-4">Employee</th>
                    <th className="py-2 pr-4">Evidence</th>
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-3 pr-4">
                        <div className="flex flex-col items-center gap-1">
                          {row.status === 'approved' ? (
                            <input
                              type="checkbox"
                              name="claimId"
                              value={row.id}
                              form="bulk-claims"
                              aria-label="Select this claim for a bulk action"
                            />
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                          {/* Persisted "translated for whom" — survives refresh. */}
                          {row.translated_langs && row.translated_langs.length > 0 && (
                            <div className="flex flex-wrap justify-center gap-0.5">
                              {row.translated_langs.map((lang) => (
                                <span
                                  key={lang}
                                  title={`Translated — visible to ${LOCALE_LABEL[lang] ?? lang} in their language`}
                                  className="rounded bg-green-100 px-1 py-0.5 text-[10px] font-medium text-green-800"
                                >
                                  ✓ {lang}
                                </span>
                              ))}
                            </div>
                          )}
                          {/* Persisted "asked to verify" — survives refresh. */}
                          {row.recert_pending && (
                            <span
                              title="A verification (recertification) request is pending for this claim"
                              className="rounded bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-800"
                            >
                              🔁 verify
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 pr-4 max-w-xs">
                        <span className="line-clamp-2">{row.summary}</span>
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
                      <td className="py-3 pr-4 text-center">{row.impact_score}</td>
                      <td className="py-3 pr-4 text-center">{row.confidence_score}</td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        {row.employee_name ?? '—'}
                      </td>
                      <td className="py-3 pr-4 max-w-xs text-xs text-muted-foreground">
                        {row.exact_quote ? (
                          <span className="line-clamp-2 italic">
                            &ldquo;{row.exact_quote}&rdquo;
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                        {new Date(row.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3">
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
