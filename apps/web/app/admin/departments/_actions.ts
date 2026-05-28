'use server';

import { revalidatePath } from 'next/cache';
import { and, eq, inArray, sql } from 'drizzle-orm';
import { z } from 'zod';
import {
  departments,
  employeeDepartments,
  employees,
} from '@oracle/db/schema';
import { getDirectDb } from '@oracle/db/client';
import { DEPARTMENTS, type Department } from '@oracle/shared';
import { requireAdmin } from '@/lib/auth-guard';

const departmentIdEnum = z.enum(
  DEPARTMENTS as unknown as [Department, ...Department[]],
);

// ---------------------------------------------------------------------------
// updateDepartment — label / description / head.
// ---------------------------------------------------------------------------

const UpdateDepartmentSchema = z.object({
  id: departmentIdEnum,
  displayLabel: z.string().min(1).max(120),
  // Empty string in the form means "clear it".
  description: z.string().max(2000),
  // 'none' (or '') means clear; otherwise a uuid that MUST already be a
  // member of this department (enforced below).
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

  // Enforce: a non-null head must be a current member of this department.
  if (headId) {
    const isMember = await db
      .select({ employeeId: employeeDepartments.employeeId })
      .from(employeeDepartments)
      .where(
        and(
          eq(employeeDepartments.departmentId, id),
          eq(employeeDepartments.employeeId, headId),
        ),
      )
      .limit(1);
    if (isMember.length === 0) {
      return {
        ok: false,
        error: 'Selected head is not a member of this department. Add them as a member first.',
      };
    }
  }

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
  revalidatePath('/admin/employees');
  return { ok: true };
}

// ---------------------------------------------------------------------------
// addDepartmentMember — add one employee to this department.
//
// Writes the join row, then syncs the legacy employees.departments text[]
// to include the department's display label (retrieval-plan reads the text[]
// today). Idempotent on both sides.
// ---------------------------------------------------------------------------

const MemberMutationSchema = z.object({
  departmentId: departmentIdEnum,
  employeeId: z.string().uuid(),
});

export type MemberMutationState = {
  ok: boolean;
  error?: string;
};

export async function addDepartmentMember(
  _prev: MemberMutationState,
  formData: FormData,
): Promise<MemberMutationState> {
  await requireAdmin();
  const db = getDirectDb();

  const parsed = MemberMutationSchema.safeParse({
    departmentId: formData.get('departmentId'),
    employeeId: formData.get('employeeId'),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { departmentId, employeeId } = parsed.data;

  try {
    const [dept] = await db
      .select({ label: departments.displayLabel })
      .from(departments)
      .where(eq(departments.id, departmentId))
      .limit(1);
    if (!dept) return { ok: false, error: 'Department not found.' };

    await db.transaction(async (tx) => {
      await tx
        .insert(employeeDepartments)
        .values({ employeeId, departmentId })
        .onConflictDoNothing();

      // Append display label to legacy text[] if not already present.
      await tx
        .update(employees)
        .set({
          departments: sql`(
            SELECT array_agg(DISTINCT x)
            FROM unnest(${employees.departments} || ARRAY[${dept.label}]::text[]) AS x
          )`,
        })
        .where(eq(employees.id, employeeId));
    });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin/departments');
  revalidatePath('/admin/employees');
  return { ok: true };
}

// ---------------------------------------------------------------------------
// removeDepartmentMember — pull one employee off this department.
//
// Also clears `departments.head_employee_id` if the removed employee was the
// head (otherwise we'd have an inconsistent "head who isn't a member" state).
// ---------------------------------------------------------------------------

export async function removeDepartmentMember(
  _prev: MemberMutationState,
  formData: FormData,
): Promise<MemberMutationState> {
  await requireAdmin();
  const db = getDirectDb();

  const parsed = MemberMutationSchema.safeParse({
    departmentId: formData.get('departmentId'),
    employeeId: formData.get('employeeId'),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { departmentId, employeeId } = parsed.data;

  try {
    const [dept] = await db
      .select({ label: departments.displayLabel, headEmployeeId: departments.headEmployeeId })
      .from(departments)
      .where(eq(departments.id, departmentId))
      .limit(1);
    if (!dept) return { ok: false, error: 'Department not found.' };

    await db.transaction(async (tx) => {
      await tx
        .delete(employeeDepartments)
        .where(
          and(
            eq(employeeDepartments.departmentId, departmentId),
            eq(employeeDepartments.employeeId, employeeId),
          ),
        );

      // Remove display label from legacy text[].
      await tx
        .update(employees)
        .set({
          departments: sql`array_remove(${employees.departments}, ${dept.label})`,
        })
        .where(eq(employees.id, employeeId));

      // Clear head if this employee was it.
      if (dept.headEmployeeId === employeeId) {
        await tx
          .update(departments)
          .set({ headEmployeeId: null })
          .where(eq(departments.id, departmentId));
      }
    });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin/departments');
  revalidatePath('/admin/employees');
  return { ok: true };
}
