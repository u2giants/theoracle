// R10.5 — Entity registry (read-only). Lists every row in the canonical
// `entities` table grouped by entity_type. Distinguishes licensors from
// vendors per the R3.5 structural rule.

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type EntityRow = {
  id: string;
  entity_type: string;
  canonical_value: string;
  display_label: string | null;
  aliases: unknown;
  domain_hints: unknown;
  created_at: string;
  claim_use_count: number;
};

// Group order: business-critical types first.
const TYPE_ORDER = [
  'customer',
  'licensor',
  'system',
  'factory',
  'freight_provider',
  'testing_lab',
  'packaging_supplier',
  'service_provider',
  'vendor',
  'department',
  'geography',
  'process_stage',
  'document_class',
  'person',
  'sku_or_product_line',
] as const;

export default async function AdminTaxonomyEntitiesPage() {
  const db = getDirectDb();

  const result = await db.execute(sql`
    SELECT
      e.id, e.entity_type, e.canonical_value, e.display_label,
      e.aliases, e.domain_hints, e.created_at,
      COALESCE((SELECT COUNT(*) FROM claim_entities ce WHERE ce.entity_id = e.id), 0) AS claim_use_count
    FROM entities e
    ORDER BY e.entity_type, e.canonical_value
  `);
  const rows = [...result] as unknown as EntityRow[];

  const grouped = new Map<string, EntityRow[]>();
  for (const row of rows) {
    const list = grouped.get(row.entity_type) ?? [];
    list.push(row);
    grouped.set(row.entity_type, list);
  }

  const orderedTypes = [
    ...TYPE_ORDER.filter((t) => grouped.has(t)),
    ...[...grouped.keys()].filter((t) => !TYPE_ORDER.includes(t as (typeof TYPE_ORDER)[number])),
  ];

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Entity registry</h1>
        <p className="text-sm text-muted-foreground">
          Layer 3 of the three-layer taxonomy. <strong>licensor</strong> is a first-class type
          distinct from <strong>vendor</strong>; operating-vendor subtypes
          (factory / freight_provider / testing_lab / packaging_supplier / service_provider)
          are also enumerated. Edit aliases or domain hints by inserting via SQL or the
          forthcoming admin actions; auto-creation is prohibited and must go through the
          entity_proposals queue.
        </p>
      </header>

      {orderedTypes.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No entities</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            The registry is empty. Run <code className="rounded bg-muted px-1 py-0.5 text-xs">
              pnpm db:migrate
            </code>{' '}
            to apply the R3.5 seed (
            <code className="rounded bg-muted px-1 py-0.5 text-xs">17_entities_seed.sql</code>).
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {orderedTypes.map((type) => {
            const items = grouped.get(type) ?? [];
            return (
              <Card key={type}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    <span className="font-mono text-xs text-muted-foreground">{type}</span>
                    <span className="ml-2 text-xs text-muted-foreground">({items.length})</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <table className="w-full text-xs">
                    <thead className="border-b text-left">
                      <tr>
                        <th className="py-2">Canonical</th>
                        <th>Display</th>
                        <th>Aliases</th>
                        <th>Domain hints</th>
                        <th className="text-right">Claims</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((e) => {
                        const aliases = Array.isArray(e.aliases) ? (e.aliases as string[]) : [];
                        const domainHints = Array.isArray(e.domain_hints)
                          ? (e.domain_hints as string[])
                          : [];
                        return (
                          <tr key={e.id} className="border-b">
                            <td className="py-2 font-mono">{e.canonical_value}</td>
                            <td>{e.display_label ?? '—'}</td>
                            <td className="text-muted-foreground">
                              {aliases.length > 0 ? aliases.join(', ') : '—'}
                            </td>
                            <td className="text-muted-foreground">
                              {domainHints.length > 0 ? domainHints.join(', ') : '—'}
                            </td>
                            <td className="text-right">{Number(e.claim_use_count)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
