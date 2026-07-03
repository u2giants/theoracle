import { and, asc, desc, eq, inArray } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  documents,
  employees,
  knowledgeTopDomains,
  sourceGroups,
  sourceOutlineSources,
  sourceOutlines,
} from '@oracle/db/schema';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';
import { generateSourceOutline } from './_actions';
import { AdminDocumentUpload } from './_components/admin-document-upload';

export const dynamic = 'force-dynamic';

export default async function AdminDocumentsPage() {
  const db = getDirectDb();
  const rows = await db
    .select({
      id: documents.id,
      fileName: documents.fileName,
      fileType: documents.fileType,
      status: documents.status,
      uploadedBy: employees.name,
      storagePath: documents.storagePath,
      createdAt: documents.createdAt,
      processedAt: documents.processedAt,
      processingError: documents.processingError,
      macroHealth: documents.macroHealth,
      context: documents.context,
    })
    .from(documents)
    .leftJoin(employees, eq(documents.uploaderId, employees.id))
    .orderBy(desc(documents.createdAt))
    .limit(100);

  const domains = await db
    .select({
      id: knowledgeTopDomains.id,
      name: knowledgeTopDomains.name,
      description: knowledgeTopDomains.description,
      belongsHere: knowledgeTopDomains.belongsHere,
      doesNotBelongHere: knowledgeTopDomains.doesNotBelongHere,
      commonEntityHints: knowledgeTopDomains.commonEntityHints,
    })
    .from(knowledgeTopDomains)
    .where(eq(knowledgeTopDomains.isActive, true))
    .orderBy(asc(knowledgeTopDomains.displayOrder));

  const documentIds = rows.map((row) => row.id);
  const outlineRows =
    documentIds.length > 0
      ? await db
          .select({
            id: sourceOutlines.id,
            documentId: sourceOutlineSources.documentId,
            status: sourceOutlines.status,
            summary: sourceOutlines.summary,
            createdAt: sourceOutlines.createdAt,
          })
          .from(sourceOutlines)
          .innerJoin(
            sourceOutlineSources,
            eq(sourceOutlineSources.sourceOutlineId, sourceOutlines.id),
          )
          .where(
            and(
              eq(sourceOutlineSources.sourceType, 'document'),
              inArray(sourceOutlineSources.documentId, documentIds),
            ),
          )
          .orderBy(desc(sourceOutlines.createdAt))
      : [];
  const outlineIds = outlineRows.map((row) => row.id);
  const groupRows =
    outlineIds.length > 0
      ? await db
          .select({
            outlineId: sourceGroups.sourceOutlineId,
            id: sourceGroups.id,
            title: sourceGroups.title,
            groupType: sourceGroups.groupType,
          })
          .from(sourceGroups)
          .where(inArray(sourceGroups.sourceOutlineId, outlineIds))
          .orderBy(asc(sourceGroups.sortOrder))
      : [];
  const groupsByOutline = new Map<string, typeof groupRows>();
  for (const group of groupRows) {
    const existing = groupsByOutline.get(group.outlineId) ?? [];
    existing.push(group);
    groupsByOutline.set(group.outlineId, existing);
  }
  const latestOutlineByDocument = new Map<string, (typeof outlineRows)[number]>();
  for (const outline of outlineRows) {
    if (outline.documentId && !latestOutlineByDocument.has(outline.documentId)) {
      latestOutlineByDocument.set(outline.documentId, outline);
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Upload company and process documents here. Each file is parsed,
          chunked, and run through claim extraction in the background — no chat
          channel required.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload documents</CardTitle>
          <CardDescription>
            Knowledge is extracted automatically. High-impact claims and new
            entities go to the review queues before they become permanent.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AdminDocumentUpload domains={domains} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} documents</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="py-2 pr-4">File</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Macro</th>
                <th className="py-2 pr-4">Uploaded by</th>
                <th className="py-2 pr-4">Uploaded</th>
                <th className="py-2 pr-4">Processed</th>
                <th className="py-2 pr-4">What is this?</th>
                <th className="py-2 pr-4">Outline</th>
                <th className="py-2 pr-4">Details</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const outline = latestOutlineByDocument.get(d.id);
                const outlineGroups = outline ? groupsByOutline.get(outline.id) ?? [] : [];
                return (
                  <tr key={d.id} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-medium">{d.fileName}</td>
                    <td className="py-2 pr-4">{d.fileType}</td>
                    <td className="py-2 pr-4">{d.status}</td>
                    <td className="py-2 pr-4">
                      <MacroHealthBadge value={d.macroHealth} />
                    </td>
                    <td className="py-2 pr-4">{d.uploadedBy ?? '—'}</td>
                    <td className="py-2 pr-4">
                      {formatNYDateTime(d.createdAt)}
                    </td>
                    <td className="py-2 pr-4">
                      {d.processedAt ? formatNYDateTime(d.processedAt) : '—'}
                    </td>
                    <td className="max-w-xs py-2 pr-4 align-top">
                      {d.context ? (
                        <details className="group">
                          <summary className="cursor-pointer list-none text-xs font-medium text-foreground underline underline-offset-2">
                            View upload note
                          </summary>
                          <div className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-2 text-xs text-foreground">
                            {d.context}
                          </div>
                        </details>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="max-w-md py-2 pr-4 align-top">
                      <div className="space-y-2">
                        {outline ? (
                          <details>
                            <summary className="cursor-pointer list-none text-xs font-medium text-foreground underline underline-offset-2">
                              {outline.status} · {formatNYDateTime(outline.createdAt)}
                            </summary>
                            <div className="mt-2 space-y-2 rounded-md border bg-muted/40 p-2 text-xs">
                              <p className="whitespace-pre-wrap">{outline.summary}</p>
                              {outlineGroups.length > 0 ? (
                                <ul className="space-y-1">
                                  {outlineGroups.slice(0, 8).map((group) => (
                                    <li key={group.id}>
                                      <span className="font-medium">{group.title}</span>{' '}
                                      <span className="text-muted-foreground">
                                        ({group.groupType})
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                              ) : null}
                            </div>
                          </details>
                        ) : (
                          <span className="text-xs text-muted-foreground">No outline yet.</span>
                        )}
                        <form action={generateSourceOutline}>
                          <input type="hidden" name="documentId" value={d.id} />
                          <input type="hidden" name="force" value={outline ? 'true' : 'false'} />
                          <Button size="sm" variant="outline" type="submit">
                            {outline ? 'Regenerate outline' : 'Generate outline'}
                          </Button>
                        </form>
                      </div>
                    </td>
                    <td className="max-w-md py-2 pr-4 align-top">
                      {d.processingError ? (
                        <details className="group">
                          <summary className="cursor-pointer list-none text-xs font-medium text-red-700 underline underline-offset-2">
                            {plainDocumentStatusMessage(d.status, d.processingError)}
                          </summary>
                          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-md border bg-red-50 p-2 text-xs text-red-950">
                            {d.processingError}
                          </pre>
                        </details>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {d.status === 'processing' || d.status === 'pending_processing'
                            ? 'Waiting for the ingestion worker.'
                            : '—'}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function MacroHealthBadge({ value }: { value: string | null }) {
  const health = value ?? 'not_applicable';
  const styles: Record<string, string> = {
    complete: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    pending: 'border-sky-200 bg-sky-50 text-sky-800',
    degraded: 'border-amber-200 bg-amber-50 text-amber-800',
    failed: 'border-red-200 bg-red-50 text-red-800',
    not_applicable: 'border-muted bg-muted/40 text-muted-foreground',
  };
  const labels: Record<string, string> = {
    complete: 'Complete',
    pending: 'Pending',
    degraded: 'Degraded',
    failed: 'Failed',
    not_applicable: 'Not run',
  };
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded border px-2 py-0.5 text-xs font-medium ${
        styles[health] ?? styles.not_applicable
      }`}
      title="Holistic source-outline, macro-relationship, and coverage-audit health"
    >
      {labels[health] ?? health}
    </span>
  );
}

function plainDocumentStatusMessage(status: string, error: string): string {
  const lower = error.toLowerCase();
  if (lower.includes('unsupported file type')) {
    return 'The file type is not supported yet.';
  }
  if (lower.includes('storage download failed')) {
    return 'The worker could not read the uploaded file from storage.';
  }
  if (lower.includes('file parse failed')) {
    return 'The file uploaded, but Oracle could not read its contents.';
  }
  if (lower.includes('no text extracted')) {
    return 'Oracle could not find readable text in this file.';
  }
  if (lower.includes('schema validation')) {
    return 'The AI returned an unexpected extraction format.';
  }
  if (status === 'failed') {
    return 'Processing failed. Open for technical details.';
  }
  return 'Processed with a warning. Open for technical details.';
}
