'use server';

import { revalidatePath } from 'next/cache';
import { z } from 'zod';
import { employees } from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { requireAdmin } from '@/lib/auth-guard';

const AddEmployeeSchema = z.object({
  name: z.string().min(1).max(255),
  email: z.string().email().max(320),
  role: z.string().min(1).max(255),
  // Comma-separated list of departments, e.g. "Creative, Production"
  departmentsRaw: z.string().min(1),
  isAdmin: z.boolean(),
});

export type AddEmployeeState = {
  ok: boolean;
  error?: string;
};

export async function addEmployee(
  _prev: AddEmployeeState,
  formData: FormData,
): Promise<AddEmployeeState> {
  await requireAdmin();
  const db = getDirectDb();

  const parsed = AddEmployeeSchema.safeParse({
    name: formData.get('name'),
    email: formData.get('email'),
    role: formData.get('role'),
    departmentsRaw: formData.get('departments'),
    isAdmin: formData.get('isAdmin') === 'true',
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { name, email, role, departmentsRaw, isAdmin } = parsed.data;
  const departments = departmentsRaw
    .split(',')
    .map((d) => d.trim())
    .filter(Boolean);

  if (departments.length === 0) {
    return { ok: false, error: 'At least one department is required.' };
  }

  try {
    await db
      .insert(employees)
      .values({
        name,
        email,
        role,
        // Keep legacy field populated for any code that still reads it.
        department: departments[0],
        departments,
        isAdmin,
      })
      .onConflictDoNothing({ target: employees.email });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin');
  return { ok: true };
}
