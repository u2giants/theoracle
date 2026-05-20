import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function AdminGapsPlaceholder() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Gaps</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p>Phase 5 — pending.</p>
        <p>
          Backed by the <code>open_gaps_by_employee</code> view. Will surface open gaps
          per employee/department and let the admin promote, demote, or resolve a gap.
        </p>
      </CardContent>
    </Card>
  );
}
