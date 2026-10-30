import Link from 'next/link';
import { requireEmployee } from '@/lib/auth-guard';
import { EntityPanel } from '../../_components/entity-panel';

export const dynamic = 'force-dynamic';

export default async function EntityPage({ params }: { params: Promise<{ id: string }> }) {
  await requireEmployee();
  const { id } = await params;
  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      <EntityPanel entityId={id} />
    </main>
  );
}
