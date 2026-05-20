// Sign-out endpoint. Accepts POST to avoid CSRF accidents from prefetchers.
// Clears the Supabase Auth session cookies server-side, then redirects home.

import { NextResponse, type NextRequest } from 'next/server';
import { getServerSupabase } from '@/lib/supabase/server';

export async function POST(request: NextRequest) {
  const supabase = await getServerSupabase();

  // signOut() invalidates the Supabase JWT and clears the auth cookies via the
  // cookie adapter in getServerSupabase. Errors here are non-fatal — we still
  // want to land the user on the login screen.
  await supabase.auth.signOut().catch((err) => {
    console.error('[auth/signout] signOut error (continuing):', err);
  });

  return NextResponse.redirect(new URL('/', request.url), { status: 303 });
}
