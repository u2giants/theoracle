import { requireEmployee } from '@/lib/auth-guard';
import { CommunityView } from '../../_components/community-view';

export const dynamic = 'force-dynamic';

export default async function CommunityPage({ params }: { params: Promise<{ id: string }> }) {
  await requireEmployee();
  const { id } = await params;
  return <CommunityView communityId={id} />;
}
