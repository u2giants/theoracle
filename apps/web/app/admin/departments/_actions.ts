'use server';

import { revalidatePath } from 'next/cache';
import { eq } from 'drizzle-orm';
import { z } from 'zod';
import { departments } from '@oracle/db/schema';
import { getDirectDb } from '@oracle/db/client';
import { DEPARTMENTS, type Department } from '@oracle/shared';
import { requireAdmin } from '@/lib/auth-guard';

const UpdateDepartmentSchema = z.object({
  id: z.enum(DEPARTMENTS as unknown as [Department, ...Department[]]),
  displayLabel: z.string().min(1).max(120),
  // Empty string in the form means "clear it".
  description: z.string().max(2000),
  // 'none' (or '') means clear; otherwise a uuid.
  headEmployeeId: z.string(),
});

export type UpdateDepartmentState = {
  ok: boolean;
  error?: string;
};

export async function updateDepartment(
  _prev: UpdateDepartmentState,
  formData: FormData,
): Promise<UpdateDepartmentState> {
  await requireAdmin();
  const db = getDirectDb();

  const parsed = UpdateDepartmentSchema.safeParse({
    id: formData.get('id'),
    displayLabel: formData.get('displayLabel'),
    description: formData.get('description') ?? '',
    headEmployeeId: formData.get('headEmployeeId') ?? '',
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { id, displayLabel, description, headEmployeeId } = parsed.data;
  const headId = headEmployeeId && headEmployeeId !== 'none' ? headEmployeeId : null;

  try {
    await db
      .update(departments)
      .set({
        displayLabel,
        description: description.trim() === '' ? null : description,
        headEmployeeId: headId,
      })
      .where(eq(departments.id, id));
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin/departments');
  return { ok: true };
}
