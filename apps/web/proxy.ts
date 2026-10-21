// Next.js 16 proxy (formerly "middleware") — spec Part 3.4 (client/server trust boundary).
//
// Ordinary non-static requests call supabase.auth.getUser() so that:
//   1. An expiring access token is silently refreshed by @supabase/ssr before it
//      hits any server component or route handler.
//   2. The refreshed token is written back to both the request (so server
//      components see the new value) and the response (so the browser's cookie
//      store is updated).
//
// Ordinary routes retain per-route authentication through auth-guard.ts.
// The exact protected control route additionally bounds refresh inside one
// original clock window; its handler still independently verifies identity.
//
// Reference: https://supabase.com/docs/guides/auth/server-side/nextjs

import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
import { captureControlWindow, controlWindowRemaining, CONTROL_PATH, CONTROL_WINDOW_HEADER, CONTROL_BYPASS_HEADERS, unavailableControl, privateControlHeaders, type ControlWindow } from './lib/replacement-control-window';
import { canonicalJson, instant, readInstalledBinding } from './lib/replacement-server-binding';
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
  if(request.nextUrl.pathname===CONTROL_PATH)return protectedControlProxy(request,captureControlWindow());
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


/** Only this exact ordinary route changes. The native branch above remains the
 * first boundary, and ordinary auth/cookie refresh below stays unchanged. */
async function protectedControlProxy(request:NextRequest,window:Readonly<ControlWindow>):Promise<Response>{
  if(request.method!=='POST')return unavailableControl(405);
  if(CONTROL_BYPASS_HEADERS.some(key=>request.headers.has(key)))return unavailableControl();
  const controller=new AbortController();let active=true,timer:ReturnType<typeof setTimeout>|undefined;
  const stop=()=>controller.abort();request.signal.addEventListener('abort',stop,{once:true});
  try{
    const installed=readInstalledBinding(),profile=installed.profile;
    const remaining=()=>{
      if(!active||request.signal.aborted)return fail();
      const ms=Math.min(controlWindowRemaining(window),instant(profile.expires_at)-Date.now(),instant(profile.original_horizon)-Date.now());
      if(ms<=0)return fail();return Math.max(1,Math.floor(ms));
    };
    if(request.headers.get('origin')!==profile.web_origin||new URL(request.url).origin!==profile.web_origin)return unavailableControl();
    const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if(!url||url!==profile.project_url||!key)return unavailableControl();
    remaining();
    // An inbound context can only be overwritten; no supplied value is trusted.
    request.headers.set(CONTROL_WINDOW_HEADER,canonicalJson(window));
    const next=()=>{const response=NextResponse.next({request:{headers:new Headers(request.headers)}});for(const [k,v]of Object.entries(privateControlHeaders))response.headers.set(k,v);return response;};
    let response=next();
    const refreshedCookies=new Map<string,{name:string;value:string;options:CookieOptions}>();
    timer=setTimeout(stop,remaining());
    const client=createServerClient(url,key,{
      global:{fetch:async(input,init)=>{
        remaining();const signals=[controller.signal,request.signal];if(init?.signal)signals.push(init.signal);if(input instanceof Request)signals.push(input.signal);
        const result=await fetch(input,{...init,signal:AbortSignal.any(signals)});remaining();return result;
      }},
      cookies:{getAll(){return request.cookies.getAll();},setAll(cookies){
        remaining();
        cookies.forEach(({name,value})=>request.cookies.set(name,value));
        cookies.forEach(cookie=>refreshedCookies.set(cookie.name,cookie));
        response=next();for(const {name,value,options}of refreshedCookies.values())response.cookies.set(name,value,options);
      }},
    });
    if(Reflect.get(client,'supabaseUrl')!==profile.project_url)return unavailableControl();
    const result=await Promise.race([client.auth.getUser(),new Promise<never>((_,reject)=>{
      const rejectAbort=()=>reject(new Error('Replacement control unavailable'));controller.signal.addEventListener('abort',rejectAbort,{once:true});if(controller.signal.aborted)rejectAbort();
    })]);
    remaining();if(result.error||!result.data.user||result.data.user.id!==profile.auth_user_id)return unavailableControl();
    if(canonicalJson(readInstalledBinding().profile)!==canonicalJson(profile))return unavailableControl();
    remaining();return response;
  }catch{return unavailableControl();}
  finally{active=false;if(timer)clearTimeout(timer);controller.abort();request.signal.removeEventListener('abort',stop);}
}
function fail():never{throw new Error('Replacement control unavailable');}

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
