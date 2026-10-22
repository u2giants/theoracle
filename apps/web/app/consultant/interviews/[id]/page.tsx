import { requireEmployee } from '@/lib/auth-guard';
import { notFound } from 'next/navigation';
import { InterviewPanel } from '@/components/consultant/interview-panel';
export const dynamic='force-dynamic';
export default async function InterviewPage({params}:{params:Promise<{id:string}>}){await requireEmployee();const {id}=await params;if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id))notFound();return <main className="mx-auto max-w-3xl space-y-4 p-6"><h1 className="text-2xl font-semibold">Your conversation</h1><InterviewPanel key={id} threadId={id}/></main>;}
