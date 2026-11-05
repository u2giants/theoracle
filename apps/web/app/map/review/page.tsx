import Link from 'next/link';
import { requireAdmin } from '@/lib/auth-guard';
import { ReviewClient } from './_components/review-client';

export const dynamic = 'force-dynamic';

export default async function MapReviewPage() {
  await requireAdmin();
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">Review flags</h1>
        <p className="text-sm text-muted-foreground">
          Everything marked wrong on the map. Resolve what you have checked.
        </p>
      </div>
      <ReviewClient />
    </main>
  );
}
