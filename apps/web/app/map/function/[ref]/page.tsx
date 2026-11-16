import { requireEmployee } from '@/lib/auth-guard';
import { FunctionView } from '../../_components/function-view';

export const dynamic = 'force-dynamic';

// Repair C5: one page per business function — its report, its processes, its
// sub-topics, its people and its open gaps.
export default async function FunctionPage({ params }: { params: Promise<{ ref: string }> }) {
  const me = await requireEmployee();
  const { ref } = await params;
  return (
    <FunctionView
      functionRef={ref}
      isAdmin={me.isAdmin}
      lang={me.locale === 'zh-CN' ? 'zh-CN' : ''}
    />
  );
}
