import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function AdminBrainPlaceholder() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Brain</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p>Phase 5 — pending.</p>
        <p>
          Backed by the <code>latest_brain_sections</code> view. Will let the admin
          browse versioned brain sections, view their structured diffs, and approve or
          reject synthesis runs (spec Part 9.8 validation rules).
        </p>
      </CardContent>
    </Card>
  );
}
