/** Node-only narrowing context. No identity, admission, capability or grant. */
import { performance } from 'node:perf_hooks';
import { canonicalJson, parseClosedJson } from './replacement-server-binding';
if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
export const CONTROL_PATH = '/api/consultant/replacement/v1/protected/control';
export const CONTROL_WINDOW_HEADER = 'x-oracle2-control-window';
export const CONTROL_BYPASS_HEADERS = Object.freeze(['x-middleware-subrequest','x-invoke-path','x-invoke-query','x-matched-path','x-now-route-matches','x-nextjs-data']);
export interface ControlWindow { readonly wall_start: number; readonly wall_end: number; readonly mono_end: string; readonly clock_domain: string; }
export interface ClockSnapshot { readonly wall: number; readonly mono: bigint; readonly domain: string; }
const unavailable = (): never => { throw new Error('Replacement control unavailable'); };
const clock = (): ClockSnapshot => ({wall:Date.now(),mono:process.hrtime.bigint(),domain:`${process.pid}:${performance.timeOrigin}`});
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
