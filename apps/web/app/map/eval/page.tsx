import { requireEmployee } from '@/lib/auth-guard';
import { EvalClient } from '../_components/eval-client';

export const dynamic = 'force-dynamic';

export default async function MapEvalPage() {
  const me = await requireEmployee();
  return <EvalClient isAdmin={me.isAdmin} />;
}
