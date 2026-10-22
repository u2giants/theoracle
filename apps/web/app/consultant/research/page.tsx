import {requireEmployee} from '@/lib/auth-guard';
import {IndustryResearchPanel} from '@/components/consultant/industry-research-panel';
export const dynamic='force-dynamic';
export default async function IndustryResearchPage(){await requireEmployee();return <main className="mx-auto max-w-4xl space-y-4 p-6"><h1 className="text-2xl font-semibold">Research and outside references</h1><IndustryResearchPanel/></main>;}
