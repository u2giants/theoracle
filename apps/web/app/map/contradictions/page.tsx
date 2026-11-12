import { requireEmployee } from '@/lib/auth-guard';
import { ContradictionsClient } from '../_components/contradictions-client';

export const dynamic = 'force-dynamic';

// Contradictions across sources (repair plan D3): open conflicts and the
// recorded timeline changes D2 can consume. Any signed-in employee may read.
export default async function MapContradictionsPage() {
  await requireEmployee();
  return <ContradictionsClient />;
}
