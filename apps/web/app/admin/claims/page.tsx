// Phase 5 placeholder — admin review queue.
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function AdminClaimsPlaceholder() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Claims</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p>Phase 5 — pending.</p>
        <p>
          This tab will show the claim review queue: pending claims with their evidence,
          approve/reject actions, and the evidence viewer linking back to messages and
          document chunks.
        </p>
        <p>
          For now, claims are read from the <code>claims_pending_review_with_evidence</code>{' '}
          view (see <code>packages/db/migrations/sql/30_admin_views.sql</code>).
        </p>
      </CardContent>
    </Card>
  );
}
