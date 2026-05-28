'use server';

import { revalidatePath } from 'next/cache';
import { eq, inArray } from 'drizzle-orm';
import { z } from 'zod';
import { employees, employeeDepartments, departments } from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { DEPARTMENTS, type Department } from '@oracle/shared';
import { requireAdmin } from '@/lib/auth-guard';

const departmentIdEnum = z.enum(
  DEPARTMENTS as unknown as [Department, ...Department[]],
);

const AddEmployeeSchema = z.object({
  name: z.string().min(1).max(255),
  email: z.string().email().max(320),
  role: z.string().min(1).max(255),
  // One or more department enum IDs, from a checkbox set.
  departmentIds: z.array(departmentIdEnum).min(1, 'At least one department is required.'),
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
    departmentIds: formData.getAll('departmentIds'),
    isAdmin: formData.get('isAdmin') === 'true',
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { name, email, role, departmentIds, isAdmin } = parsed.data;

  try {
    // Fetch display labels so the legacy text[] column carries human-readable
    // values (retrieval-plan.ts uses them as soft RRF hints — see the
    // comments on the employees.departments column in schema.ts).
    const labelRows = await db
      .select({ id: departments.id, label: departments.displayLabel })
      .from(departments)
      .where(inArray(departments.id, departmentIds));
    const labelById = new Map(labelRows.map((r) => [r.id, r.label]));
    const orderedLabels = departmentIds.map((id) => labelById.get(id) ?? id);

    await db.transaction(async (tx) => {
      const [inserted] = await tx
        .insert(employees)
        .values({
          name,
          email,
          role,
          department: orderedLabels[0],
          departments: orderedLabels,
          isAdmin,
        })
        .onConflictDoNothing({ target: employees.email })
        .returning({ id: employees.id });

      if (inserted) {
        await tx.insert(employeeDepartments).values(
          departmentIds.map((departmentId) => ({
            employeeId: inserted.id,
            departmentId,
          })),
        );
      }
    });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin');
  revalidatePath('/admin/departments');
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Edit an existing employee's department membership.
// Overwrites the legacy employees.departments text[] AND the
// employee_departments join table in a single transaction.
// ---------------------------------------------------------------------------

const UpdateEmployeeDepartmentsSchema = z.object({
  employeeId: z.string().uuid(),
  departmentIds: z.array(departmentIdEnum),
});

export type UpdateEmployeeDepartmentsState = {
  ok: boolean;
  error?: string;
};

export async function updateEmployeeDepartments(
  _prev: UpdateEmployeeDepartmentsState,
  formData: FormData,
): Promise<UpdateEmployeeDepartmentsState> {
  await requireAdmin();
  const db = getDirectDb();

  const parsed = UpdateEmployeeDepartmentsSchema.safeParse({
    employeeId: formData.get('employeeId'),
    departmentIds: formData.getAll('departmentIds'),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { employeeId, departmentIds } = parsed.data;

  try {
    const labelRows = departmentIds.length > 0
      ? await db
          .select({ id: departments.id, label: departments.displayLabel })
          .from(departments)
          .where(inArray(departments.id, departmentIds))
      : [];
    const labelById = new Map(labelRows.map((r) => [r.id, r.label]));
    const orderedLabels = departmentIds.map((id) => labelById.get(id) ?? id);

    await db.transaction(async (tx) => {
      await tx.delete(employeeDepartments).where(eq(employeeDepartments.employeeId, employeeId));
      if (departmentIds.length > 0) {
        await tx.insert(employeeDepartments).values(
          departmentIds.map((departmentId) => ({
            employeeId,
            departmentId,
          })),
        );
      }
      await tx
        .update(employees)
        .set({
          department: orderedLabels[0] ?? null,
          departments: orderedLabels,
        })
        .where(eq(employees.id, employeeId));
    });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin');
  revalidatePath('/admin/departments');
  return { ok: true };
}
