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
import { nativeRequestAllowed, nativeForwardingAllowed, readStaticManifest } from './lib/native-browser-runtime.mjs';

export async function proxy(request: NextRequest) {
  // Candidate-only server boundary precedes all retained Supabase/company code.
  // Every ordinary Vercel deployment keeps the existing path when flag is absent.
  if(process.env.ORACLE2_NATIVE_BROWSER_ONLY!==undefined){
    try{
      if(['x-middleware-subrequest','x-invoke-path','x-invoke-query','x-matched-path','x-now-route-matches','x-nextjs-data'].some(key=>request.headers.has(key)))return new NextResponse('Unavailable',{status:404,headers:{'Cache-Control':'no-store'}});
      if(!nativeForwardingAllowed(request.headers.get('host'),request.headers.get('x-forwarded-proto'),request.headers.get('x-forwarded-host'),request.headers.get('forwarded'),process.env))return new NextResponse('Unavailable',{status:404,headers:{'Cache-Control':'no-store'}});
      if(!nativeRequestAllowed(request.url,request.method,request.headers.get('host'),process.env,readStaticManifest()))
        return new NextResponse('Unavailable',{status:404,headers:{'Cache-Control':'no-store'}});
      return NextResponse.next({request});
    }catch{return new NextResponse('Unavailable',{status:503,headers:{'Cache-Control':'no-store'}});}
  }
  // Preserve the original matcher exclusions for ordinary deployments.
  if(/^\/(?:_next\/(?:static|image)|favicon\.ico|robots\.txt|sitemap\.xml)/.test(request.nextUrl.pathname)
    ||/\.(?:svg|png|jpg|jpeg|gif|webp)$/.test(request.nextUrl.pathname))return NextResponse.next({request});
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
    '/:path*',
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
