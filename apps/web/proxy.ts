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
import { captureControlWindow, controlWindowRemaining,isConversationPath, CONTROL_PATH, CONNECTED_ANSWER_PATH, CONNECTED_MCP_PATH, MEETING_CONTROL_PATH, MEETING_INGRESS_PATH, ORIGINAL_VIEW_PATH, ORIGINAL_UPLOAD_PATH, MODEL_REVIEW_PATH, CONTROL_WINDOW_HEADER, CONTROL_BYPASS_HEADERS, unavailableControl, privateControlHeaders, type ControlWindow } from './lib/replacement-control-window';
import { canonicalJson, instant, admitEmployeeRecipientOriginV1, employeeRecipientIndexConfiguredV1, readInstalledEmployeeBindingV1, rereadInstalledEmployeeBindingV1, installedEmployeeRecipientHorizonV1, type EmployeeBindingPurposeV1, readInstalledBinding, readInstalledViewerBinding, readInstalledUploadBinding,readInstalledModelReviewBinding,readInstalledConversationBinding,readInstalledConnectedAnswerBinding,readInstalledMcpAnswerBinding,readInstalledMeetingBinding } from './lib/replacement-server-binding';
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
  if(request.nextUrl.pathname===MEETING_INGRESS_PATH&&process.env.ORACLE2_MEETING_ROUTING_MODE==='replacement'){
    const window=captureControlWindow();if(request.method!=='POST')return unavailableControl(405);
    if(CONTROL_BYPASS_HEADERS.some(k=>request.headers.has(k)))return unavailableControl();
    request.headers.set(CONTROL_WINDOW_HEADER,canonicalJson(window));
    return NextResponse.next({request:{headers:new Headers(request.headers)}});
  }
  if(request.nextUrl.pathname===MEETING_CONTROL_PATH||request.nextUrl.pathname===CONNECTED_ANSWER_PATH||request.nextUrl.pathname===CONNECTED_MCP_PATH||request.nextUrl.pathname===CONTROL_PATH||request.nextUrl.pathname===ORIGINAL_VIEW_PATH||request.nextUrl.pathname===ORIGINAL_UPLOAD_PATH||request.nextUrl.pathname===MODEL_REVIEW_PATH||isConversationPath(request.nextUrl.pathname))return protectedControlProxy(request,captureControlWindow());
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
  const upload=request.nextUrl.pathname===ORIGINAL_UPLOAD_PATH;
  const conversation=isConversationPath(request.nextUrl.pathname);
  const viewer=request.nextUrl.pathname===ORIGINAL_VIEW_PATH||upload;
  if(viewer&&['range','if-range','if-match','if-none-match','if-modified-since','if-unmodified-since','expect','content-encoding'].some(k=>request.headers.has(k)))return unavailableControl();
  if(CONTROL_BYPASS_HEADERS.some(key=>request.headers.has(key)))return unavailableControl();
  const controller=new AbortController();let active=true,timer:ReturnType<typeof setTimeout>|undefined;
  const stop=()=>controller.abort();request.signal.addEventListener('abort',stop,{once:true});
  try{
    const readBinding=request.nextUrl.pathname===MEETING_CONTROL_PATH?readInstalledMeetingBinding:request.nextUrl.pathname===CONNECTED_ANSWER_PATH?readInstalledConnectedAnswerBinding:request.nextUrl.pathname===CONNECTED_MCP_PATH?readInstalledMcpAnswerBinding:conversation?readInstalledConversationBinding:request.nextUrl.pathname===MODEL_REVIEW_PATH?readInstalledModelReviewBinding:upload?readInstalledUploadBinding:viewer?readInstalledViewerBinding:readInstalledBinding;
    const indexed=employeeRecipientIndexConfiguredV1();
    // Static indexed origins restrict before auth; identity selection remains after real SDK and employee SQL.
    // The retained singleton path still checks its installed origin before auth.
    let installed:ReturnType<typeof readBinding>|ReturnType<typeof readInstalledEmployeeBindingV1>|undefined=indexed?undefined:readBinding();
    let profile=installed?.profile;
    const kind:EmployeeBindingPurposeV1=request.nextUrl.pathname===MEETING_CONTROL_PATH?'meeting':request.nextUrl.pathname===CONNECTED_ANSWER_PATH?'answer':request.nextUrl.pathname===CONNECTED_MCP_PATH?'mcp-answer':conversation?'conversation':request.nextUrl.pathname===MODEL_REVIEW_PATH?'review':upload?'upload':viewer?'viewer':'control';
    const configuredProject=process.env.NEXT_PUBLIC_SUPABASE_URL;
    const originRestriction=indexed?admitEmployeeRecipientOriginV1(kind,configuredProject??'',request.headers.get('origin'),request.url):undefined;
    if(originRestriction){
      const end=Math.floor(Math.min(window.wall_end,originRestriction.validUntil));
      window=Object.freeze({...window,wall_end:end,mono_end:(BigInt(window.mono_end)-BigInt(Math.ceil((window.wall_end-end)*1e6))).toString()});
    }
    const remaining=()=>{
      if(!active||request.signal.aborted)return fail();
      const ms=Math.min(controlWindowRemaining(window),originRestriction?originRestriction.validUntil-Date.now():Infinity,profile?instant(profile.expires_at)-Date.now():Infinity,profile?instant(profile.original_horizon)-Date.now():Infinity,installed?installedEmployeeRecipientHorizonV1(installed)-Date.now():Infinity);
      if(ms<=0)return fail();return Math.max(1,Math.floor(ms));
    };
    const originMatches=()=>profile&&request.headers.get('origin')===profile.web_origin&&new URL(request.url).origin===profile.web_origin;
    if(!indexed&&!originMatches())return unavailableControl();
    const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if(!url||!key||(!indexed&&url!==profile!.project_url))return unavailableControl();
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
    const actualProjectUrl:unknown=Reflect.get(client,'supabaseUrl');if(actualProjectUrl!==url)return unavailableControl();
    const aborted=()=>new Promise<never>((_,reject)=>{
      const rejectAbort=()=>reject(new Error('Replacement control unavailable'));controller.signal.addEventListener('abort',rejectAbort,{once:true});if(controller.signal.aborted)rejectAbort();
    });
    const result=await Promise.race([client.auth.getUser(),aborted()]);
    remaining();if(result.error||!result.data.user)return unavailableControl();
    if(indexed){
      const {getUniqueEmployeeForAuthUserV1}=await Promise.race([import('./lib/auth-guard'),aborted()]);remaining();
      const employee=await Promise.race([getUniqueEmployeeForAuthUserV1(result.data.user.id),aborted()]);remaining();
      if(!employee)return proxyDiag('no-employee');
      installed=readInstalledEmployeeBindingV1(kind,{configuredProjectUrl:url,actualProjectUrl,verifiedUserId:result.data.user.id,employeeId:employee.id,disabledAt:employee.disabledAt});profile=installed.profile;
      if(timer)clearTimeout(timer);timer=setTimeout(stop,remaining());
      remaining();if(!originMatches()||url!==profile.project_url)return proxyDiag('origin-mismatch');
      const currentEmployee=await Promise.race([getUniqueEmployeeForAuthUserV1(result.data.user.id),aborted()]);remaining();
      if(!currentEmployee||currentEmployee.id!==profile.employee_id||currentEmployee.disabledAt!==null||canonicalJson(rereadInstalledEmployeeBindingV1(installed)?.profile)!==canonicalJson(profile)){console.error('ORACLE-DIAG proxy employee-recheck fail');return unavailableControl();}
    }else{
      if(result.data.user.id!==profile!.auth_user_id)return unavailableControl();
      if(canonicalJson(readBinding().profile)!==canonicalJson(profile))return unavailableControl();
    }
    remaining();return response;
  }catch(err){console.error('ORACLE-DIAG proxy catch',err instanceof Error?err.stack||err.message:String(err));return unavailableControl();}
  finally{active=false;if(timer)clearTimeout(timer);controller.abort();request.signal.removeEventListener('abort',stop);}
}
function fail():never{throw new Error('Replacement control unavailable');}
function proxyDiag(reason:string):Response{console.error('ORACLE-DIAG proxy refuse',reason);return unavailableControl();}

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
