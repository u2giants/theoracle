// Root page — landing / sign-in entry.
// For an authenticated approved employee, redirect to /channels.
// For an authenticated unapproved user, send to /denied.
// For everyone else, render the login form.

import { redirect } from 'next/navigation';
import { eq } from 'drizzle-orm';
import { getServerSupabase } from '@/lib/supabase/server';
import { getDirectDb } from '@oracle/db/client';
import { employees } from '@oracle/db/schema';
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
    try {
      const db = getDirectDb();
      const rows = await db
        .select()
        .from(employees)
        .where(eq(employees.authUserId, userId))
        .limit(1);
      const me = rows[0];
      if (me && !me.disabledAt) {
        if (me.isAdmin) redirect('/admin');
        redirect('/channels');
      }
      // signed in but no approved employee row
      redirect('/denied');
    } catch (err) {
      // DB env missing — fall through.
      console.error('[home] DB lookup failed:', err);
    }
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
