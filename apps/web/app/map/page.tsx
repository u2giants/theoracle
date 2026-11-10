import { requireEmployee } from '@/lib/auth-guard';
import { MapHome } from './_components/map-home';

export const dynamic = 'force-dynamic';

export default async function MapHomePage() {
  const me = await requireEmployee();
  return <MapHome isAdmin={me.isAdmin} lang={me.locale === 'zh-CN' ? 'zh-CN' : ''} />;
}
