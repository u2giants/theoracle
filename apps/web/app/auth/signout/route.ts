// Sign-out endpoint. Accepts POST to avoid CSRF accidents from prefetchers.
// Clears the Supabase Auth session cookies server-side, then redirects home.

import { NextResponse, type NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { createServerClient, type CookieOptions } from '@supabase/ssr';

export async function POST(request: NextRequest) {
  const cookieStore = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        get(name: string) {
          return cookieStore.get(name)?.value;
        },
        set(name: string, value: string, options: CookieOptions) {
          cookieStore.set({ name, value, ...options });
        },
        remove(name: string, options: CookieOptions) {
          cookieStore.set({ name, value: '', ...options, maxAge: 0 });
        },
      },
    },
  );

  // signOut() invalidates the Supabase JWT and clears the auth cookies via the
  // CookieAdapter above. Errors here are non-fatal — we still want to land the
  // user on the login screen.
  await supabase.auth.signOut().catch((err) => {
    console.error('[auth/signout] signOut error (continuing):', err);
  });

  return NextResponse.redirect(new URL('/', request.url), { status: 303 });
}
