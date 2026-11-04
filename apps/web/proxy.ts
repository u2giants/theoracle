// Next.js 16 proxy (formerly "middleware").
//
// Calls supabase.auth.getUser() on every non-static request so an expiring
// access token is refreshed by @supabase/ssr and written back to both the
// request (for server components) and the response (for the browser).
// Per-route authentication stays in lib/auth-guard.ts.
//
// Reference: https://supabase.com/docs/guides/auth/server-side/nextjs
import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function proxy(request: NextRequest): Promise<Response> {
  let supabaseResponse = NextResponse.next({ request });

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  // Without Supabase env (CI builds, placeholder URL) pass through.
  if (!supabaseUrl || !supabaseAnonKey || supabaseUrl.includes('example.supabase.co')) {
    return supabaseResponse;
  }

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          supabaseResponse.cookies.set(name, value, options),
        );
      },
    },
  });

  // Use getUser(), not getSession(): getUser() validates with Supabase Auth
  // and refreshes an expired token. Must run unconditionally.
  await supabase.auth.getUser();
  return supabaseResponse;
}

export const config = {
  matcher: [
    // Everything except Next.js static files, images and common static assets.
    '/((?!_next/static|_next/image|favicon\\.ico|robots\\.txt|sitemap\\.xml|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
