import { requireEmployee } from '@/lib/auth-guard';
import { CommunityView } from '../../_components/community-view';

export const dynamic = 'force-dynamic';

export default async function CommunityPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await requireEmployee();
  const { id } = await params;
  return (
    <CommunityView
      communityId={id}
      isAdmin={me.isAdmin}
      lang={me.locale === 'zh-CN' ? 'zh-CN' : ''}
    />
  );
}
