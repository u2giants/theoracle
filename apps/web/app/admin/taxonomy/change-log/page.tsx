// R10.5 — Read-only audit view of taxonomy_change_log.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

type LogRow = {
  id: string;
  change_type: string;
  before_state: unknown;
  after_state: unknown;
  reason: string | null;
  approver_name: string | null;
  proposal_id: string | null;
  created_at: string;
};

export default async function AdminTaxonomyChangeLogPage() {
  const db = getDirectDb();

  const result = await db.execute(sql`
    SELECT
      l.id, l.change_type, l.before_state, l.after_state, l.reason,
      e.name AS approver_name, l.proposal_id, l.created_at
    FROM taxonomy_change_log l
    LEFT JOIN employees e ON e.id = l.approved_by_employee_id
    ORDER BY l.created_at DESC
    LIMIT 200
  `);
  const rows = [...result] as unknown as LogRow[];

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Change log</h1>
        <p className="text-sm text-muted-foreground">
          Append-only audit of every accepted taxonomy change. Reads from{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">taxonomy_change_log</code>.
          Latest 200 events.
        </p>
      </header>

      {rows.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No changes recorded yet</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            The log is empty. It populates the first time an admin approves or rejects a
            proposal.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="space-y-3 pt-4">
            {rows.map((r) => (
              <div
                key={r.id}
                className="rounded border-l-2 border-muted bg-muted/30 px-3 py-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-foreground">{r.change_type}</span>
                  <span className="text-muted-foreground">
                    {formatNYDateTime(r.created_at)}
                    {r.approver_name && <> · {r.approver_name}</>}
                  </span>
                </div>
                {r.reason && <div className="mt-1 italic">{r.reason}</div>}
                {r.proposal_id && (
                  <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                    proposal {r.proposal_id.slice(0, 8)}…
                  </div>
                )}
                <details className="mt-1">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
                    JSON
                  </summary>
                  <pre className="mt-1 overflow-x-auto rounded bg-background p-2 font-mono text-[10px]">
                    {JSON.stringify(
                      { before_state: r.before_state, after_state: r.after_state },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
