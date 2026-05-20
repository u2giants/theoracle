// Root page — landing / sign-in entry.
// For an authenticated approved employee, redirect to /channels.
// For an authenticated unapproved user, send to /denied.
// For everyone else, render the login form.

import { redirect } from 'next/navigation';
import { eq } from 'drizzle-orm';
import { getServerSupabase } from '@/lib/supabase/server';
import { getDirectDb } from '@oracle/db/client';
import { employees, employeeIdentities } from '@oracle/db/schema';
import { LoginForm } from './_components/login-form';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  let userId: string | null = null;
  try {
    const supabase = await getServerSupabase();
    const { data } = await supabase.auth.getUser();
    userId = data.user?.id ?? null;
  } catch {
    // Supabase env missing — see DECISIONS.md D0.4. Fall through to login screen.
  }

  if (userId) {
    // Look up the employee row WITHOUT wrapping redirect() in the try/catch.
    // Next.js implements redirect() by throwing a NEXT_REDIRECT exception that the
    // framework catches at the request boundary. Swallowing it here prevents the
    // redirect and surfaces the throw to the dev overlay.
    let target: '/admin' | '/channels' | '/denied' = '/denied';
    try {
      const db = getDirectDb();
      // Resolve employee through identities (post D2.multi-identity).
      const rows = await db
        .select({ employee: employees })
        .from(employees)
        .innerJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
        .where(eq(employeeIdentities.authUserId, userId))
        .limit(1);
      const me = rows[0]?.employee;
      if (me && !me.disabledAt) {
        target = me.isAdmin ? '/admin' : '/channels';
      }
    } catch (err) {
      console.error('[home] DB lookup failed:', err);
      // Fall through to /denied — safer to deny than to leak an unverified session.
    }
    redirect(target);
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>The Oracle</CardTitle>
          <CardDescription>
            Operations intelligence for POP Creations / Spruce Line. Sign in with your
            company email to continue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
      </Card>
    </main>
  );
}
