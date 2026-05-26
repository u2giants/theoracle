'use server';

import { eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { claims } from '@oracle/db/schema';

export async function updateClaimStatus(formData: FormData) {
  // Defense in depth: server actions can be invoked by any authenticated user
  // via a crafted POST regardless of the /admin/* layout guard. Authorize at
  // the action boundary — matching the taxonomy/_actions.ts pattern.
  await requireAdmin();

  const id = formData.get('id') as string;
  const status = formData.get('status') as 'approved' | 'rejected';
  if (!id || !['approved', 'rejected'].includes(status)) return;

  const db = getDirectDb();
  await db.update(claims).set({ status }).where(eq(claims.id, id));
  revalidatePath('/admin/claims');
}
