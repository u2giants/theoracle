import { requireEmployee } from '@/lib/auth-guard';
import { FunctionsClient } from '../_components/functions-client';

export const dynamic = 'force-dynamic';

export default async function MapFunctionsPage() {
  const me = await requireEmployee();
  return <FunctionsClient isAdmin={me.isAdmin} />;
}
