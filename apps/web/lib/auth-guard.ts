// Server-side auth guard helpers used by route segments.
// Server Components call requireEmployee()/requireAdmin() to either fetch
// the current employee row or redirect.

import { redirect } from 'next/navigation';
import { eq } from 'drizzle-orm';
import { getServerSupabase } from '@/lib/supabase/server';
import { getDirectDb } from '@oracle/db/client';
import { employees, type Employee } from '@oracle/db/schema';

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
    const rows = await db
      .select()
      .from(employees)
      .where(eq(employees.authUserId, userId))
      .limit(1);
    const me = rows[0];
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
