// OAuth / magic-link callback — spec Part 4.4 implementation.
//
// 1. Exchange the code for a session.
// 2. Resolve the verified user.
// 3. Call linkOrRejectEmployee — looks up an employee_identities row by
//    (auth_provider, auth_user_id); if none exists, falls back to matching
//    employees.email to bootstrap a new identity row. Updates last_login_at.
//    See DECISIONS.md D2.multi-identity.
// 4. Redirect:
//      ok       → /channels  (or /admin if isAdmin)
//      denied   → /denied
//      hijack   → /denied?reason=hijack_attempt

import { NextResponse, type NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { linkOrRejectEmployee } from '@oracle/auth/link';
import { resolveAuthProvider } from '@oracle/auth/server';

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const next = url.searchParams.get('next') ?? '/';

  // Diagnostics — when an OAuth provider denies/errors it usually sends ?error=…
  // back instead of a code. Log everything so we can see what arrived.
  if (!code) {
    const oauthError = url.searchParams.get('error');
    const oauthErrorDescription = url.searchParams.get('error_description');
    const oauthErrorUri = url.searchParams.get('error_uri');
    console.error('[auth/callback] no code in callback. Full URL:', request.url);
    console.error('[auth/callback] params:', Object.fromEntries(url.searchParams));
    if (oauthError) {
      console.error('[auth/callback] provider error:', {
        error: oauthError,
        description: oauthErrorDescription,
        uri: oauthErrorUri,
      });
    }
    return NextResponse.redirect(new URL('/denied?reason=no_code', url.origin));
  }

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

  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
  if (exchangeError) {
    console.error('[auth/callback] exchangeCodeForSession failed', exchangeError);
    return NextResponse.redirect(
      new URL('/denied?reason=exchange_failed', url.origin),
    );
  }

  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) {
    return NextResponse.redirect(new URL('/denied?reason=no_user', url.origin));
  }

  const user = userData.user;
  if (!user.email || !user.email_confirmed_at) {
    return NextResponse.redirect(
      new URL('/denied?reason=unverified_email', url.origin),
    );
  }

  const link = await linkOrRejectEmployee({
    authUserId: user.id,
    email: user.email,
    authProvider: resolveAuthProvider(user),
    authProviderSubject:
      typeof user.user_metadata?.sub === 'string'
        ? (user.user_metadata.sub as string)
        : user.id,
  });

  if (!link.ok) {
    // Drop the session so a denied user doesn't sit on the cookie.
    await supabase.auth.signOut();
    return NextResponse.redirect(new URL(`/denied?reason=${link.reason}`, url.origin));
  }

  const target = link.employee.isAdmin ? '/admin' : next === '/' ? '/channels' : next;
  return NextResponse.redirect(new URL(target, url.origin));
}
