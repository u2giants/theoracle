// Next.js 16 proxy (formerly "middleware") — spec Part 3.4 (client/server trust boundary).
//
// Runs on every non-static request. Its ONLY job is to call supabase.auth.getUser()
// so that:
//   1. An expiring access token is silently refreshed by @supabase/ssr before it
//      hits any server component or route handler.
//   2. The refreshed token is written back to both the request (so server
//      components see the new value) and the response (so the browser's cookie
//      store is updated).
//
// This proxy does NOT enforce authentication — that is done per-route by
// requireEmployee() / requireAdmin() in lib/auth-guard.ts.
//
// Reference: https://supabase.com/docs/guides/auth/server-side/nextjs

import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function proxy(request: NextRequest) {
  // Start with a clean pass-through response.
  let supabaseResponse = NextResponse.next({ request });

  // Skip when the Supabase URL is missing (CI placeholder builds, etc.).
  // Auth enforcement still happens in requireEmployee() per-route.
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnonKey || supabaseUrl.includes('example.supabase.co')) {
    return supabaseResponse;
  }

  const supabase = createServerClient(
    supabaseUrl,
    supabaseAnonKey,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          // Mutate the request so any downstream middleware/handler sees new values.
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          // Rebuild the response to propagate Set-Cookie headers to the browser.
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // IMPORTANT: use getUser(), not getSession().
  // getSession() trusts the locally-stored token without server validation;
  // getUser() calls Supabase Auth and triggers a refresh when the token has expired.
  // Do NOT await inside any condition before this call — it must run unconditionally.
  await supabase.auth.getUser();

  return supabaseResponse;
}

export const config = {
  matcher: [
    /*
     * Match every path EXCEPT:
     *  - _next/static  (Next.js build assets)
     *  - _next/image   (image optimisation)
     *  - favicon.ico, robots.txt, sitemap.xml
     *  - Image extensions (svg, png, jpg, jpeg, gif, webp)
     */
    '/((?!_next/static|_next/image|favicon\\.ico|robots\\.txt|sitemap\\.xml|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
