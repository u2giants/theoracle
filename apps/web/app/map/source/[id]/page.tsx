import { requireEmployee } from '@/lib/auth-guard';
import { SourceViewer } from '../../_components/source-viewer';

export const dynamic = 'force-dynamic';

export default async function SourcePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ chunk?: string }>;
}) {
  await requireEmployee();
  const { id } = await params;
  const { chunk } = await searchParams;
  return <SourceViewer sourceId={id} chunkId={chunk ?? null} />;
}
