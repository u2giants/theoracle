import {notFound} from 'next/navigation';
import {requireEmployee} from '@/lib/auth-guard';
import {QualifiedWorkspace} from '@/components/consultant/qualified-workspace';
export const dynamic='force-dynamic';
export default async function WorkspacePage(){await requireEmployee();if(process.env.ORACLE2_WORKSPACE_ENABLED!=='true')notFound();return <QualifiedWorkspace/>;}
