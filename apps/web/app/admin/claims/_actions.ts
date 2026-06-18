'use server';

import { eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { claims } from '@oracle/db/schema';
import { triggerTask } from '@/lib/trigger';

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

/**
 * Bilingual claim layer (china_imp.md): translate the SELECTED claims into the
 * other supported language(s) for the China team. Translation is opt-in per
 * claim — not every approved claim is shared with China — so this is a manual
 * bulk action, not an automatic on-approval trigger. The worker is idempotent
 * (re-running is safe) and skips claims that aren't approved.
 */
export async function translateClaimsForChina(formData: FormData) {
  await requireAdmin();

  const ids = Array.from(
    new Set(
      formData
        .getAll('claimId')
        .filter((v): v is string => typeof v === 'string' && v.length > 0),
    ),
  );
  if (ids.length === 0) return;

  // Fire-and-forget per claim; triggerTask swallows transport errors and the
  // worker is idempotent, so partial failures are safe to re-submit.
  for (const id of ids) {
    await triggerTask('claim-translation', { claimId: id });
  }

  revalidatePath('/admin/claims');
}
