'use server';

import { eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { gaps } from '@oracle/db/schema';

export async function updateGapStatus(formData: FormData) {
  // Defense in depth — see claims/_actions.ts for rationale.
  await requireAdmin();

  const id = formData.get('id') as string;
  const status = formData.get('status') as 'resolved' | 'stale' | 'rejected';
  if (!id || !['resolved', 'stale', 'rejected'].includes(status)) return;

  const db = getDirectDb();
  await db.update(gaps).set({ status }).where(eq(gaps.id, id));
  revalidatePath('/admin/gaps');
}
