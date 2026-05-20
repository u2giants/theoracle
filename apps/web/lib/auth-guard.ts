// Server-side auth guard helpers used by route segments.
// Server Components call requireEmployee()/requireAdmin() to either fetch
// the current employee row or redirect.

import { redirect } from 'next/navigation';
import { eq } from 'drizzle-orm';
import { getServerSupabase } from '@/lib/supabase/server';
import { getDirectDb } from '@oracle/db/client';
import { employees, employeeIdentities, type Employee } from '@oracle/db/schema';

export async function getCurrentEmployee(): Promise<Employee | null> {
  let userId: string | null = null;
  try {
    const supabase = await getServerSupabase();
    const { data } = await supabase.auth.getUser();
    userId = data.user?.id ?? null;
  } catch {
    return null;
  }
  if (!userId) return null;

  try {
    const db = getDirectDb();
    // Resolve the employee through employee_identities (post DECISIONS.md
    // D2.multi-identity — auth_user_id no longer lives on employees).
    const rows = await db
      .select({ employee: employees })
      .from(employees)
      .innerJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
      .where(eq(employeeIdentities.authUserId, userId))
      .limit(1);
    const me = rows[0]?.employee;
    if (!me || me.disabledAt) return null;
    return me;
  } catch (err) {
    console.error('[auth-guard] DB lookup failed:', err);
    return null;
  }
}

export async function requireEmployee(): Promise<Employee> {
  const me = await getCurrentEmployee();
  if (!me) redirect('/');
  return me;
}

export async function requireAdmin(): Promise<Employee> {
  const me = await requireEmployee();
  if (!me.isAdmin) redirect('/channels');
  return me;
}
