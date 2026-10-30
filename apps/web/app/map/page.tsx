import { requireEmployee } from '@/lib/auth-guard';
import { MapHome } from './_components/map-home';

export const dynamic = 'force-dynamic';

export default async function MapHomePage() {
  await requireEmployee();
  return <MapHome />;
}
