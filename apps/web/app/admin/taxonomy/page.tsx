// R10.5 — Top-level domains list (landing tab).

export const dynamic = 'force-dynamic';

import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type DomainRow = {
  id: string;
  name: string;
  description: string;
  belongs_here: unknown;
  does_not_belong_here: unknown;
  common_entity_hints: unknown;
  default_excluded_document_classes: unknown;
  neighboring_domain_ids: unknown;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  // Counts joined in below.
  claim_count: number;
  document_count: number;
  chunk_count: number;
  message_count: number;
};

export default async function AdminTaxonomyPage() {
  const db = getDirectDb();

  const result = await db.execute(sql`
    SELECT
      d.id, d.name, d.description,
      d.belongs_here, d.does_not_belong_here, d.common_entity_hints,
      d.default_excluded_document_classes, d.neighboring_domain_ids,
      d.display_order, d.is_active, d.created_at, d.updated_at,
      COALESCE((SELECT COUNT(*) FROM claim_top_domains ctd WHERE ctd.top_domain_id = d.id), 0) AS claim_count,
      COALESCE((SELECT COUNT(*) FROM document_top_domains dtd WHERE dtd.top_domain_id = d.id), 0) AS document_count,
      COALESCE((SELECT COUNT(*) FROM document_chunk_top_domains dctd WHERE dctd.top_domain_id = d.id), 0) AS chunk_count,
      COALESCE((SELECT COUNT(*) FROM message_top_domains mtd WHERE mtd.top_domain_id = d.id), 0) AS message_count
    FROM knowledge_top_domains d
    ORDER BY d.is_active DESC, d.display_order ASC
  `);
  const rows = [...result] as unknown as DomainRow[];

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Top-level knowledge domains</h1>
        <p className="text-sm text-muted-foreground">
          Layer 1 of the three-layer taxonomy. Admin-curated; auto-mutation is prohibited.
          Each domain carries boundary rules that the entity resolver and synthesis validator
          consult.
        </p>
      </header>

      <div className="space-y-3">
        {rows.map((d) => {
          const belongs = arr(d.belongs_here);
          const doesNot = arr(d.does_not_belong_here);
          const entities = arr<{ entityType: string; canonicalValue: string }>(d.common_entity_hints);
          const excluded = arr<string>(d.default_excluded_document_classes);
          const neighbors = arr<string>(d.neighboring_domain_ids);
          return (
            <Card key={d.id} className={d.is_active ? '' : 'opacity-50'}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    <span className="font-mono text-xs text-muted-foreground">{d.id}</span>{' '}
                    {d.name}
                    {!d.is_active && (
                      <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs">inactive</span>
                    )}
                  </CardTitle>
                  <div className="flex gap-2 text-xs text-muted-foreground">
                    <span>{Number(d.claim_count)} claims</span>
                    <span>·</span>
                    <span>{Number(d.document_count)} docs</span>
                    <span>·</span>
                    <span>{Number(d.chunk_count)} chunks</span>
                    <span>·</span>
                    <span>{Number(d.message_count)} messages</span>
                  </div>
                </div>
                <p className="mt-1 text-sm">{d.description}</p>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {belongs.length > 0 && (
                  <RuleBlock label="Belongs here" items={belongs.map((b) => String(b))} tone="green" />
                )}
                {doesNot.length > 0 && (
                  <RuleBlock label="Does NOT belong here" items={doesNot.map((b) => String(b))} tone="red" />
                )}
                {entities.length > 0 && (
                  <RuleBlock
                    label="Common entities"
                    items={entities.map((e) => `${e.entityType}: ${e.canonicalValue}`)}
                    tone="neutral"
                  />
                )}
                {excluded.length > 0 && (
                  <RuleBlock label="Default excluded document classes" items={excluded} tone="amber" />
                )}
                {neighbors.length > 0 && (
                  <RuleBlock label="Neighboring domains" items={neighbors} tone="neutral" />
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function RuleBlock({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone: 'green' | 'red' | 'amber' | 'neutral';
}) {
  const colorMap: Record<typeof tone, string> = {
    green: 'bg-green-50 text-green-800',
    red: 'bg-red-50 text-red-800',
    amber: 'bg-amber-50 text-amber-800',
    neutral: 'bg-muted text-muted-foreground',
  };
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="flex flex-wrap gap-1">
        {items.map((it, i) => (
          <span key={`${label}-${i}`} className={`rounded px-1.5 py-0.5 ${colorMap[tone]}`}>
            {it}
          </span>
        ))}
      </div>
    </div>
  );
}

function arr<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}
