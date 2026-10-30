import { requireAdmin } from '@/lib/auth-guard';
import { QuestionsClient } from '../_components/questions-client';

export const dynamic = 'force-dynamic';

// Open-question queue and Teams interviews (plan step 12). Admin only.
export default async function MapQuestionsPage() {
  await requireAdmin();
  return <QuestionsClient />;
}
