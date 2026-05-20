import { desc, eq } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { documents, employees } from '@oracle/db/schema';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

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
    })
    .from(documents)
    .leftJoin(employees, eq(documents.uploaderId, employees.id))
    .orderBy(desc(documents.createdAt))
    .limit(100);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Read-only list of uploaded documents. Ingestion worker runs in Phase 4.
        </p>
      </header>
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
                <th className="py-2 pr-4">Uploaded by</th>
                <th className="py-2 pr-4">Uploaded</th>
                <th className="py-2 pr-4">Processed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} className="border-b last:border-0">
                  <td className="py-2 pr-4 font-medium">{d.fileName}</td>
                  <td className="py-2 pr-4">{d.fileType}</td>
                  <td className="py-2 pr-4">{d.status}</td>
                  <td className="py-2 pr-4">{d.uploadedBy ?? '—'}</td>
                  <td className="py-2 pr-4">
                    {new Date(d.createdAt).toLocaleString()}
                  </td>
                  <td className="py-2 pr-4">
                    {d.processedAt ? new Date(d.processedAt).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
