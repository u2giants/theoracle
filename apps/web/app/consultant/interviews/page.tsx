import { requireEmployee } from '@/lib/auth-guard';
import { InterviewPanel } from '@/components/consultant/interview-panel';
export const dynamic='force-dynamic';
export default async function InterviewsPage(){await requireEmployee();return <main className="mx-auto max-w-3xl space-y-4 p-6"><h1 className="text-2xl font-semibold">Your conversations</h1><InterviewPanel /></main>;}
