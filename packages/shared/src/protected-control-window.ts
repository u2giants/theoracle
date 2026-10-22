/** Node-only narrowing context. No identity, admission, capability or grant. */
import { performance } from 'node:perf_hooks';
import { canonicalJson, parseClosedJson,readInstalledMeetingStopProcessConfigV1,currentInstalledMeetingStopProcessConfigV1,instant,type MeetingStopProcessConfigV1 } from './protected-server-binding';
if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
export const ORIGINAL_VIEW_PATH='/api/consultant/replacement/v1/protected/original';
export const MODEL_REVIEW_PATH='/api/consultant/replacement/v1/protected/model-review';
export const CONTROL_PATH = '/api/consultant/replacement/v1/protected/control';
export const CONTROL_WINDOW_HEADER = 'x-oracle2-control-window';
export const CONTROL_BYPASS_HEADERS = Object.freeze(['x-middleware-subrequest','x-invoke-path','x-invoke-query','x-matched-path','x-now-route-matches','x-nextjs-data']);
export interface ControlWindow { readonly wall_start: number; readonly wall_end: number; readonly mono_end: string; readonly clock_domain: string; }
export interface ClockSnapshot { readonly wall: number; readonly mono: bigint; readonly domain: string; }
const unavailable = (): never => { throw new Error('Replacement control unavailable'); };
const clock = (): ClockSnapshot => ({wall:Date.now(),mono:process.hrtime.bigint(),domain:`${process.pid}:${performance.timeOrigin}`});
/** Format a supplied original millisecond instant only; never reads a clock.
 * Python's canonical UTC omits zero fractions and renders nonzero six digits.
 */
export function canonicalInstantV1(milliseconds:number):string{
  if(typeof milliseconds!=='number'||!Number.isSafeInteger(milliseconds))return unavailable();
  const value=new Date(milliseconds).toISOString();
  if(!/^[0-9]{4}-/.test(value)||Number(value.slice(0,4))<1)return unavailable();
  return value.replace('.000Z','Z').replace(/\.(\d{3})Z$/,'.$1000Z');
}
export function captureControlWindow(): Readonly<ControlWindow> {
  const now=clock();return Object.freeze({wall_start:now.wall,wall_end:now.wall+30000,mono_end:String(now.mono+30000000000n),clock_domain:now.domain});
}
/** Pure descriptive arithmetic seam for clock adversarials. Production uses its
 * actual clock, never a request-selected clock or renewed remaining duration. */
export function controlWindowRemaining(window: ControlWindow, now: ClockSnapshot = clock()): number {
  if(window.clock_domain!==now.domain || window.wall_start>now.wall)return unavailable();
  const mono=BigInt(window.mono_end)-now.mono;
  if(mono<=0n || mono>30000000000n)return unavailable();
  const ms=Math.min(window.wall_end-now.wall,Number(mono)/1e6);
  if(!Number.isFinite(ms)||ms<=0)return unavailable();return Math.max(1,Math.floor(ms));
}
export function readControlWindow(headers: Headers): Readonly<ControlWindow> {
  const raw=headers.get(CONTROL_WINDOW_HEADER);if(!raw)return unavailable();
  const value=parseClosedJson(Buffer.from(raw,'utf8'),1024);
  if(!value||typeof value!=='object'||Array.isArray(value)||canonicalJson(value)!==raw)return unavailable();
  const v=value as Record<string,unknown>;
  if(Object.keys(v).sort().join(',')!=='clock_domain,mono_end,wall_end,wall_start'||typeof v.wall_start!=='number'||!Number.isSafeInteger(v.wall_start)||v.wall_start<1||typeof v.wall_end!=='number'||!Number.isSafeInteger(v.wall_end)||v.wall_end-v.wall_start!==30000||typeof v.mono_end!=='string'||! /^[1-9][0-9]{0,23}$/.test(v.mono_end)||typeof v.clock_domain!=='string'||! /^[1-9][0-9]{0,9}:[0-9]{1,16}(?:\.[0-9]{1,6})?$/.test(v.clock_domain))return unavailable();
  const result=Object.freeze(v) as unknown as Readonly<ControlWindow>;controlWindowRemaining(result);return result;
}
export const privateControlHeaders=Object.freeze({'Cache-Control':'private, no-store, max-age=0','Pragma':'no-cache','X-Content-Type-Options':'nosniff'});
export function unavailableControl(status:503|405=503):Response {
  return Response.json({error:'Replacement control unavailable'},{status,headers:status===405?{...privateControlHeaders,Allow:'POST'}:privateControlHeaders});
}

export const ORIGINAL_UPLOAD_PATH='/api/consultant/replacement/v1/protected/upload';

export const MEETING_CONTROL_PATH='/api/consultant/replacement/v1/protected/meetings/control';
export const MEETING_INGRESS_PATH='/api/teams/live/recall';
export const CONVERSATION_PATH='/api/consultant/interviews';
export function isConversationPath(path:string):boolean{return path===CONVERSATION_PATH||/^\/api\/consultant\/interviews\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/turns$/.test(path);}


export interface Window { readonly wall: number; readonly mono: number; end: number; readonly signal: AbortSignal; proxyMonoEnd: bigint; }


export const remaining = (window: Window): number => {
  const ms = Math.min(window.end - Date.now(), window.end - window.wall - (performance.now() - window.mono), Number(window.proxyMonoEnd - process.hrtime.bigint()) / 1e6);
  if (window.signal.aborted || ms <= 0) return unavailable();
  return Math.max(1, Math.floor(ms));
};


export async function within<T>(promise: Promise<T>, window: Window): Promise<T> {
  const ms = remaining(window);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let onAbort: (() => void) | undefined;
  try {
    return await Promise.race([promise,new Promise<never>((_,reject) => {
      timer = setTimeout(() => reject(new Error('Replacement control unavailable')),ms);
      onAbort = () => reject(new Error('Replacement control unavailable'));
      window.signal.addEventListener('abort',onAbort,{once:true});
      if (window.signal.aborted) onAbort();
    })]);
  } finally { if (timer) clearTimeout(timer); if (onAbort) window.signal.removeEventListener('abort',onAbort); }
}

export const CONNECTED_ANSWER_PATH='/api/consultant/replacement/v1/protected/answer';
export const CONNECTED_MCP_PATH='/api/consultant/mcp/mcp';


/** Private original local-operation provenance. Time is narrowing, no grant. */
interface LocalStopWindowRecordV1 {readonly wall:number;readonly mono:number;readonly tick:bigint;readonly hardEnd:number;readonly hardMonoEnd:bigint;readonly config:Readonly<MeetingStopProcessConfigV1>;readonly window:Window;}
const localStopWindowsV1=new WeakMap<object,LocalStopWindowRecordV1>();
const localStopMinimumEndsV1=new WeakMap<object,number>();
export function _captureLocalStopOperationV1():object{
 const wall=Date.now(),mono=performance.now(),tick=process.hrtime.bigint();
 const config=readInstalledMeetingStopProcessConfigV1();currentInstalledMeetingStopProcessConfigV1(config);
 const end=Math.floor(Math.min(wall+config.stop_request_seconds*1000,instant(config.expires_at),instant(config.stop_until),instant(config.original_horizon))),hardMonoEnd=tick+BigInt(Math.max(0,end-wall))*1000000n;
 const window:Window={wall,mono,end,signal:AbortSignal.timeout(30000),proxyMonoEnd:hardMonoEnd};
 Object.defineProperties(window,{wall:{writable:false,configurable:false},mono:{writable:false,configurable:false},signal:{writable:false,configurable:false}});
 const cap=Object.freeze({});localStopWindowsV1.set(cap,Object.freeze({wall,mono,tick,hardEnd:end,hardMonoEnd,config,window}));localStopMinimumEndsV1.set(cap,end);remaining(window);return cap;
}
export function _currentLocalStopOperationV1(cap:object):Readonly<LocalStopWindowRecordV1>{
 const v=localStopWindowsV1.get(cap),prior=localStopMinimumEndsV1.get(cap);if(!v||prior===undefined)return unavailable();v.window.end=Math.min(v.window.end,v.hardEnd,prior);localStopMinimumEndsV1.set(cap,v.window.end);const monoEnd=v.tick+BigInt(Math.max(0,Math.floor(v.window.end-v.wall)))*1000000n;v.window.proxyMonoEnd=v.window.proxyMonoEnd<monoEnd?v.window.proxyMonoEnd:monoEnd;currentInstalledMeetingStopProcessConfigV1(v.config);remaining(v.window);return v;
}
export function _narrowLocalStopOperationV1(cap:object,end:number):void{
 const v=_currentLocalStopOperationV1(cap);if(!Number.isFinite(end)||end>v.window.end)return unavailable();v.window.end=Math.min(v.window.end,end);localStopMinimumEndsV1.set(cap,v.window.end);remaining(v.window);
}
