'use server';

import { eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { contradictions } from '@oracle/db/schema';

export async function updateContradictionStatus(formData: FormData) {
  // Defense in depth — see claims/_actions.ts for rationale.
  await requireAdmin();

  const id = formData.get('id') as string;
  const status = formData.get('status') as 'open' | 'dismissed';
  if (!id || !['open', 'dismissed'].includes(status)) return;

  const db = getDirectDb();
  await db.update(contradictions).set({ status }).where(eq(contradictions.id, id));
  revalidatePath('/admin/contradictions');
}
