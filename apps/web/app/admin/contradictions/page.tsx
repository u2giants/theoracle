import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function AdminContradictionsPlaceholder() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Contradictions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p>Phase 5 — pending.</p>
        <p>
          Backed by the <code>contradictions_with_claim_summaries</code> view. Will show
          possible contradictions, both claim summaries side-by-side, the suggested
          question, and let the admin dismiss or convert into a gap.
        </p>
      </CardContent>
    </Card>
  );
}
