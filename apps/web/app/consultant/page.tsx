import Link from 'next/link';
import { PilotWorkspace } from '@/components/consultant/pilot-workspace';

export const dynamic = 'force-dynamic';

export default function ConsultantPage() {
  return <>{process.env.ORACLE2_WORKSPACE_ENABLED==='true'&&<nav aria-label="Company knowledge"><Link className="m-4 inline-block rounded border p-3 underline" href="/consultant/workspace">Company knowledge workspace · 公司知识工作区</Link></nav>}<PilotWorkspace /></>;
}
