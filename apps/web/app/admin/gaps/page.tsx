export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { desc, eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { gaps, employees } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { updateGapStatus } from './_actions';

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
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'open';

  const db = getDirectDb();

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
    .where(activeStatus !== 'all' ? eq(gaps.status, activeStatus as Parameters<typeof eq>[1]) : undefined)
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
              href={`/admin/gaps?status=${tab.value}`}
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
                        {new Date(row.createdAt).toLocaleDateString()}
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
