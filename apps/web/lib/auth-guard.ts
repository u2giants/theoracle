// Server-side auth guard helpers used by route segments.
// Server Components call requireEmployee()/requireAdmin() to either fetch
// the current employee row or redirect.

import { redirect } from 'next/navigation';
import { eq } from 'drizzle-orm';
import { getServerSupabase } from '@/lib/supabase/server';
import { getPooledDb } from '@oracle/db/client';
import { employees, employeeIdentities, type Employee } from '@oracle/db/schema';

const AUTH_LOOKUP_ATTEMPTS = 3;
const AUTH_LOOKUP_RETRY_MS = 150;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function getEmployeeForAuthUser(userId: string): Promise<Employee | null> {
  let lastError: unknown = null;

  for (let attempt = 1; attempt <= AUTH_LOOKUP_ATTEMPTS; attempt += 1) {
    try {
      const db = getPooledDb();
      // Resolve the employee through employee_identities (post DECISIONS.md
      // D2.multi-identity — auth_user_id no longer lives on employees).
      const rows = await db
        .select({ employee: employees })
        .from(employees)
        .innerJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
        .where(eq(employeeIdentities.authUserId, userId))
        .limit(1);
      return rows[0]?.employee ?? null;
    } catch (err) {
      lastError = err;
      console.error(`[auth-guard] DB lookup attempt ${attempt} failed:`, err);
      if (attempt < AUTH_LOOKUP_ATTEMPTS) {
        await sleep(AUTH_LOOKUP_RETRY_MS * attempt);
      }
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error('Employee identity lookup failed.');
}

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

  const me = await getEmployeeForAuthUser(userId);
  if (!me || me.disabledAt) return null;
  return me;
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
