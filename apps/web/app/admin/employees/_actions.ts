'use server';

import { revalidatePath } from 'next/cache';
import { eq, inArray, sql } from 'drizzle-orm';
import { z } from 'zod';
import { employees, employeeDepartments, departments } from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { DEPARTMENTS, type Department } from '@oracle/shared';
import { requireAdmin } from '@/lib/auth-guard';
import { getServiceRoleSupabase } from '@/lib/supabase/server';

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

  revalidatePath('/admin/employees');
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

  revalidatePath('/admin/employees');
  revalidatePath('/admin/departments');
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Disable / re-enable employee access.
// Soft-disable via employees.disabled_at so historical messages, claims,
// evidence, assignments, and audit records keep their employee references.
// ---------------------------------------------------------------------------

const UpdateEmployeeAccessSchema = z.object({
  employeeId: z.string().uuid(),
  action: z.enum(['disable', 'enable']),
});

export type UpdateEmployeeAccessState = {
  ok: boolean;
  error?: string;
};

export async function updateEmployeeAccess(
  _prev: UpdateEmployeeAccessState,
  formData: FormData,
): Promise<UpdateEmployeeAccessState> {
  const me = await requireAdmin();
  const db = getDirectDb();

  const parsed = UpdateEmployeeAccessSchema.safeParse({
    employeeId: formData.get('employeeId'),
    action: formData.get('action'),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { employeeId, action } = parsed.data;
  if (action === 'disable' && employeeId === me.id) {
    return { ok: false, error: 'You cannot disable your own active admin account.' };
  }

  try {
    const [target] = await db
      .select({
        id: employees.id,
        isAdmin: employees.isAdmin,
        disabledAt: employees.disabledAt,
      })
      .from(employees)
      .where(eq(employees.id, employeeId))
      .limit(1);
    if (!target) return { ok: false, error: 'Employee not found.' };

    if (action === 'disable' && target.isAdmin && !target.disabledAt) {
      const adminCountResult = await db.execute(sql`
        SELECT count(*)::int AS active_admin_count
        FROM employees
        WHERE is_admin = true
          AND disabled_at IS NULL
          AND id <> ${employeeId}::uuid
      `);
      const activeAdminCount = Number(
        ([...adminCountResult][0] as { active_admin_count?: number } | undefined)
          ?.active_admin_count ?? 0,
      );
      if (activeAdminCount < 1) {
        return { ok: false, error: 'At least one active admin must remain.' };
      }
    }

    await db
      .update(employees)
      .set({ disabledAt: action === 'disable' ? new Date() : null })
      .where(eq(employees.id, employeeId));
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  revalidatePath('/admin/employees');
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Invite a Microsoft 365 user as a new Oracle employee.
//
// Distinct from addEmployee: allows zero departments (admin assigns later)
// and triggers a Supabase admin invite email so the recipient knows they've
// been added. When they next sign in (via Microsoft SSO or magic link), the
// existing identity linker matches by email and merges them in.
// ---------------------------------------------------------------------------

const InviteFromM365Schema = z.object({
  email: z.string().email().max(320),
  name: z.string().min(1).max(255),
  // Optional at invite time. The admin will fix it via the inline editor
  // once the row exists, OR pre-pick a couple here if they already know.
  departmentIds: z.array(departmentIdEnum).optional().default([]),
  // Optional Graph-supplied job title.
  jobTitle: z.string().max(255).optional().default(''),
});

export type InviteFromM365State = {
  ok: boolean;
  error?: string;
  /** Set to true when the DB insert succeeded but the email send failed. */
  emailFailed?: boolean;
};

export async function inviteFromM365(
  _prev: InviteFromM365State,
  formData: FormData,
): Promise<InviteFromM365State> {
  await requireAdmin();
  const db = getDirectDb();

  const parsed = InviteFromM365Schema.safeParse({
    email: (formData.get('email') as string | null)?.toLowerCase().trim() ?? '',
    name: formData.get('name'),
    departmentIds: formData.getAll('departmentIds'),
    jobTitle: formData.get('jobTitle') ?? '',
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues.map((i) => i.message).join('; ') };
  }

  const { email, name, departmentIds, jobTitle } = parsed.data;
  const role = jobTitle.trim() || 'Employee';

  // Department labels (only needed when at least one was picked).
  let orderedLabels: string[] = [];
  if (departmentIds.length > 0) {
    const labelRows = await db
      .select({ id: departments.id, label: departments.displayLabel })
      .from(departments)
      .where(inArray(departments.id, departmentIds));
    const labelById = new Map(labelRows.map((r) => [r.id, r.label]));
    orderedLabels = departmentIds.map((id) => labelById.get(id) ?? id);
  }

  try {
    await db.transaction(async (tx) => {
      const [inserted] = await tx
        .insert(employees)
        .values({
          name,
          email,
          role,
          department: orderedLabels[0] ?? null,
          departments: orderedLabels,
          isAdmin: false,
        })
        .onConflictDoNothing({ target: employees.email })
        .returning({ id: employees.id });

      if (inserted && departmentIds.length > 0) {
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

  // Send the magic-link invite via Supabase admin (routes through Brevo SMTP
  // configured at the Supabase project level). Failure here is non-fatal —
  // the employee row is already in place; the admin can resend manually or
  // the user can sign in via SSO with no email.
  try {
    const supabase = getServiceRoleSupabase();
    const { error } = await supabase.auth.admin.inviteUserByEmail(email, {
      data: { invited_via: 'm365_directory_pull', display_name: name },
    });
    if (error) {
      console.error('[inviteFromM365] supabase invite email failed', error);
      revalidatePath('/admin/employees');
      return { ok: true, emailFailed: true };
    }
  } catch (err) {
    console.error('[inviteFromM365] supabase invite threw', err);
    revalidatePath('/admin/employees');
    return { ok: true, emailFailed: true };
  }

  revalidatePath('/admin/employees');
  return { ok: true };
}
