import { requireEmployee } from '@/lib/auth-guard';
import { SourcesClient } from './_components/sources-client';

export const dynamic = 'force-dynamic';

export default async function MapSourcesPage() {
  const me = await requireEmployee();
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Company Map sources</h1>
        <p className="text-sm text-muted-foreground">
          Upload procedure documents, diagrams and transcripts, or paste a
          transcript. Everything queued here is read into the company map.
        </p>
      </div>
      <SourcesClient isAdmin={me.isAdmin} />
    </main>
  );
}
