import Link from 'next/link';
import { requireEmployee } from '@/lib/auth-guard';
import { CorrectionsClient } from './_components/corrections-client';

export const dynamic = 'force-dynamic';

type PageProps = {
  searchParams: Promise<{ function?: string; from?: string }>;
};

export default async function MapCorrectionsPage({ searchParams }: PageProps) {
  const me = await requireEmployee();
  const params = await searchParams;
  const initialFunctionRef =
    typeof params.function === 'string' ? params.function : '';
  const initialPageRef = typeof params.from === 'string' ? params.from : '';

  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">Map corrections</h1>
        <p className="text-sm text-muted-foreground">
          Tell us what is wrong on the Company Map and how the process actually works.
        </p>
      </div>
      <CorrectionsClient
        isAdmin={me.isAdmin}
        initialFunctionRef={initialFunctionRef}
        initialPageRef={initialPageRef}
      />
    </main>
  );
}
