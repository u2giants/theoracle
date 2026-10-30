import { requireEmployee } from '@/lib/auth-guard';
import { AskClient } from '../_components/ask-client';

export const dynamic = 'force-dynamic';

export default async function AskPage() {
  await requireEmployee();
  return <AskClient />;
}
