import { requireEmployee } from '@/lib/auth-guard';
import { ConnectedAnswerPanel } from '@/components/consultant/connected-answer-panel';
export const dynamic='force-dynamic';
export default async function ConnectedAnswerPage(){await requireEmployee();return <main className="mx-auto max-w-4xl space-y-4 p-6"><h1 className="text-2xl font-semibold">Ask the Oracle</h1><p>Read qualified reports and their original evidence. Reports can conflict or remain uncertain.</p><div id="qualified-answer-client"><ConnectedAnswerPanel /></div></main>;}
