import { requireEmployee } from '@/lib/auth-guard';
import { RecommendationsClient } from '../_components/recommendations-client';

export const dynamic = 'force-dynamic';

// Recommendations with competing explanations (plan step 13). Everyone reads;
// admins set Accept / Reject / Running / Measured.
export default async function MapRecommendationsPage() {
  const me = await requireEmployee();
  return <RecommendationsClient isAdmin={me.isAdmin} />;
}
