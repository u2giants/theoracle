export const dynamic = 'force-dynamic';

import { getDirectDb } from '@oracle/db/client';
import { loadClaimCorrectionLessonPack } from '@oracle/ai';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';

export default async function ClaimLessonsPage() {
  const db = getDirectDb();
  const lessonPack = await loadClaimCorrectionLessonPack(db, { limit: 14 });

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Claim Correction Lessons</h1>
        <p className="text-sm text-muted-foreground">
          Approved human revisions are summarized here and injected into future
          extraction prompts as semi-stable correction guidance.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Total revisions</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {lessonPack.revisionCount}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Approved revised claims</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {lessonPack.approvedRevisionCount}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Examples in prompt</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {lessonPack.rows.length}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent approved corrections</CardTitle>
        </CardHeader>
        <CardContent>
          {lessonPack.rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No approved revisions yet. Revise a claim, then approve the replacement
              claim, to create correction lessons.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="border-b text-left uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Original</th>
                    <th className="py-2 pr-4">Corrected</th>
                    <th className="py-2 pr-4">Domains</th>
                    <th className="py-2 pr-4">Note</th>
                    <th className="py-2">When</th>
                  </tr>
                </thead>
                <tbody>
                  {lessonPack.rows.map((row) => (
                    <tr key={row.review_event_id} className="border-b last:border-0">
                      <td className="max-w-md whitespace-pre-wrap py-3 pr-4 align-top">
                        {row.original_summary}
                      </td>
                      <td className="max-w-md whitespace-pre-wrap py-3 pr-4 align-top">
                        {row.revised_summary}
                      </td>
                      <td className="max-w-56 py-3 pr-4 align-top text-muted-foreground">
                        <div>{row.original_domains?.join(', ') || '(none)'}</div>
                        <div className="mt-1 font-medium text-foreground">
                          {'->'} {row.revised_domains?.join(', ') || '(none)'}
                        </div>
                      </td>
                      <td className="max-w-sm whitespace-pre-wrap py-3 pr-4 align-top text-muted-foreground">
                        {row.reviewer_note ?? '-'}
                      </td>
                      <td className="whitespace-nowrap py-3 align-top text-muted-foreground">
                        {formatNYDateTime(row.reviewed_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Prompt block used by extraction</CardTitle>
        </CardHeader>
        <CardContent>
          {lessonPack.promptBlock ? (
            <pre className="max-h-[32rem] overflow-auto rounded border bg-muted p-3 whitespace-pre-wrap text-xs">
              {lessonPack.promptBlock}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">
              No prompt block is generated until at least one revised claim is approved.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
