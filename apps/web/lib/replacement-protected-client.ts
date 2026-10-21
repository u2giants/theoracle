/** Server-only, fixed-peer control transport. No admission, retries, result API,
 * writer capability or fixture fallback. Not wired to any route here. */
import * as https from 'node:https';
import * as tls from 'node:tls';
import { performance } from 'node:perf_hooks';
import { canonicalHash, canonicalJson, canonicalUuid, instant, matchesIdentity, parseClosedJson, readInstalledBinding, sha256, type InstalledBinding, type ServerBinding } from './replacement-server-binding';
import { readControlWindow } from './replacement-control-window';
if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
const failure = (): never => { throw new Error('Replacement control unavailable'); };
const exact = (v: unknown, fields: readonly string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v,k));
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= 2147483647;
export interface ControlMetadata {
  readonly runId: string; readonly journeyRevision: number; readonly controlState: 'pending'|'processing'|'delivered'|'revision_pending'|'cancelled'|'error'|'awaiting-external-authority'|'missing-evidence'|'cancel-requested'|'failed'|'UNKNOWN';
  readonly populationSha256: string; readonly cancelRequested: boolean; readonly remoteStopProven: false; readonly resultAvailable: false;
}
const states = new Set(['pending','processing','delivered','revision_pending','cancelled','error','awaiting-external-authority','missing-evidence','cancel-requested','failed','UNKNOWN']);
/** Descriptive wire validation; a valid DTO grants no access. */
export function parseControlMetadata(bytes: Uint8Array): Readonly<ControlMetadata> {
  const v = parseClosedJson(bytes,4096);
  if (canonicalJson(v) !== Buffer.from(bytes).toString('utf8') || !exact(v,['runId','journeyRevision','controlState','populationSha256','cancelRequested','remoteStopProven','resultAvailable']) || !canonicalUuid(v.runId) || !integer(v.journeyRevision) || typeof v.controlState !== 'string' || !states.has(v.controlState) || !canonicalHash(v.populationSha256) || typeof v.cancelRequested !== 'boolean' || v.remoteStopProven !== false || v.resultAvailable !== false) return failure();
  return Object.freeze(v) as unknown as Readonly<ControlMetadata>;
}
interface Window { readonly wall: number; readonly mono: number; end: number; readonly signal: AbortSignal; proxyMonoEnd: bigint; }
const remaining = (window: Window): number => {
  const ms = Math.min(window.end - Date.now(), window.end - window.wall - (performance.now() - window.mono), Number(window.proxyMonoEnd - process.hrtime.bigint()) / 1e6);
  if (window.signal.aborted || ms <= 0) return failure();
  return Math.max(1, Math.floor(ms));
};
async function within<T>(promise: Promise<T>, window: Window): Promise<T> {
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
async function identity(binding: Readonly<ServerBinding>, window: Window): Promise<void> {
  // The sole production adapter: no supplied snapshot, JWT decoding, role,
  // fixture cookie, service client or caller-selected identity can enter here.
  const { getServerSupabase } = await within(import('./supabase/server'),window);
  const client = await within(getServerSupabase(),window);
  const { data, error } = await within(client.auth.getUser(),window);
  if (error || !data.user?.id) return failure();
  const { getEmployeeForAuthUser } = await within(import('./auth-guard'),window);
  const employee = await within(getEmployeeForAuthUser(data.user.id),window);
  // Supabase exposes this actual configured property at runtime but marks it
  // protected in its TypeScript class; validate the value without a type cast.
  const actualProjectUrl: unknown = Reflect.get(client, 'supabaseUrl');
  if (typeof actualProjectUrl !== 'string') return failure();
  if (!employee || !matchesIdentity(binding, { configuredProjectUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? '', actualProjectUrl, verifiedUserId:data.user.id,employeeId:employee.id,disabledAt:employee.disabledAt })) return failure();
  remaining(window);
}
function current(initial: InstalledBinding, window: Window): void {
  const again = readInstalledBinding();
  if (canonicalJson(again.profile) !== canonicalJson(initial.profile)) return failure();
  window.end = Math.min(window.end,instant(again.profile.expires_at),instant(again.profile.original_horizon));
  remaining(window);
}
function origin(request: Request, binding: Readonly<ServerBinding>): void {
  if (request.method !== 'POST' || request.headers.get('origin') !== binding.web_origin || new URL(request.url).origin !== binding.web_origin || request.headers.get('content-type') !== 'application/json' || request.headers.has('content-encoding')) return failure();
}
async function readBody(request: Request, window: Window): Promise<Buffer> {
  const declared = request.headers.get('content-length');
  if (declared !== null && (!/^[1-9][0-9]{0,4}$/.test(declared) || Number(declared) > 65536)) return failure();
  if (!request.body) return failure();
  const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let length = 0;
  try {
    for (;;) {
      const next = await within(reader.read(),window); if (next.done) break;
      length += next.value.length; if (length > 65536) return failure(); chunks.push(next.value);
    }
    if (!length || (declared !== null && Number(declared) !== length)) return failure();
    return Buffer.concat(chunks,length);
  } finally { void reader.cancel().catch(() => undefined); reader.releaseLock(); }
}
/** Exact Python requester wire, including the unchanged caller narrowing value. */
export function validateControlRequest(bytes: Uint8Array): Readonly<Record<string, unknown>> {
  const v = parseClosedJson(bytes,65536);
  if (!v || typeof v !== 'object' || Array.isArray(v)) return failure();
  const p = v as Record<string,unknown>;
  const common = ['schema_version','operation','caller_deadline'];
  if (p.schema_version !== 1 || typeof p.operation !== 'string') return failure();
  instant(p.caller_deadline);
  if (p.operation === 'reserve') {
    if (!exact(p,[...common,'source_selectors','population_sha256','idempotency_key']) || !canonicalHash(p.population_sha256) || !canonicalUuid(p.idempotency_key) || !Array.isArray(p.source_selectors) || p.source_selectors.length < 1 || p.source_selectors.length > 100) return failure();
    const seen = new Set<string>();
    for (const s of p.source_selectors) {
      if (!exact(s,['source_id','revision']) || !canonicalUuid(s.source_id) || !integer(s.revision) || seen.has(s.source_id)) return failure();
      seen.add(s.source_id);
    }
  } else if (p.operation === 'status') {
    if (!exact(p,[...common,'run_id']) || !canonicalUuid(p.run_id)) return failure();
  } else if (p.operation === 'cancel') {
    if (!exact(p,[...common,'run_id','expected_revision','reason','idempotency_key']) || !canonicalUuid(p.run_id) || !integer(p.expected_revision) || !canonicalUuid(p.idempotency_key) || typeof p.reason !== 'string' || [...p.reason].length < 1 || [...p.reason].length > 1600) return failure();
  } else return failure();
  if (canonicalJson(p) !== Buffer.from(bytes).toString('utf8')) return failure();
  return Object.freeze(p);
}

async function transport(installed: InstalledBinding, body: Buffer, window: Window): Promise<Readonly<ControlMetadata>> {
  const p = installed.profile; const url = new URL(p.backend_origin);
  let socket: tls.TLSSocket | undefined; let request: ReturnType<typeof https.request> | undefined;
  const abort = () => { request?.destroy(); socket?.destroy(); };
  window.signal.addEventListener('abort',abort,{once:true});
  try {
    socket = tls.connect({host:p.server_dns,port:url.port ? Number(url.port) : 443,servername:p.server_dns,ca:installed.ca,cert:installed.cert,key:installed.key,rejectUnauthorized:true,minVersion:'TLSv1.2',ALPNProtocols:['http/1.1'],checkServerIdentity:(host,cert) => tls.checkServerIdentity(host,cert) ?? (sha256(cert.raw) === p.server_certificate_der_sha256 ? undefined : new Error('Replacement control unavailable'))});
    socket.on('error',() => undefined);
    socket.setTimeout(remaining(window),() => socket?.destroy(new Error('Replacement control unavailable')));
    await within(new Promise<void>((resolve,reject) => { socket!.once('secureConnect',() => {
      try {
        if (!socket!.authorized || tls.checkServerIdentity(p.server_dns,socket!.getPeerCertificate()) || sha256(socket!.getPeerCertificate().raw) !== p.server_certificate_der_sha256 || (socket!.alpnProtocol && socket!.alpnProtocol !== 'http/1.1')) return reject(new Error('Replacement control unavailable'));
        resolve();
      } catch { reject(new Error('Replacement control unavailable')); }
    }); socket!.once('error',reject); socket!.once('close',() => reject(new Error('Replacement control unavailable'))); }),window);
    // No HTTP bytes exist until chain, hostname and actual leaf DER pass.
    current(installed,window);
    await identity(p,window);
    current(installed,window);
    const connected = socket;
    const agent = new https.Agent({keepAlive:false,maxSockets:1});
    agent.createConnection = () => connected;
    try {
      const response = new Promise<Readonly<ControlMetadata>>((resolve,reject) => {
        let metadata: Readonly<ControlMetadata> | undefined; let ended = false; let peerEnded = false; let responseCount = 0;
        const refuse = () => reject(new Error('Replacement control unavailable'));
        connected.once('end',() => { peerEnded = true; });
        connected.once('close',(hadError) => { if (hadError || !peerEnded || !ended || !metadata) refuse(); else resolve(metadata); });
        request = https.request({protocol:'https:',hostname:p.server_dns,port:url.port || 443,path:p.control_path,method:'POST',agent,headers:{'Content-Type':'application/json','Content-Length':String(body.length),'Connection':'close'}},res => {
          responseCount++; if (responseCount !== 1 || res.statusCode !== 200 || res.headers['content-type'] !== 'application/json' || res.headers['content-encoding'] !== undefined || res.headers['transfer-encoding'] !== undefined || res.headers.connection !== 'close') { refuse(); abort(); return; }
          const seen = new Set<string>();
          for (let i = 0; i < res.rawHeaders.length; i += 2) { const h = res.rawHeaders[i]!.toLowerCase(); if (seen.has(h)) { refuse(); abort(); return; } seen.add(h); }
          const len = res.headers['content-length'];
          if (typeof len !== 'string' || !/^[1-9][0-9]{0,3}$/.test(len) || Number(len) > 4096) { refuse(); abort(); return; }
          let size = 0; const chunks: Buffer[] = [];
          res.on('data',(chunk: Buffer) => {
            try { connected.setTimeout(remaining(window),() => abort()); size += chunk.length; if (size > Number(len)) throw new Error(); chunks.push(chunk); }
            catch { refuse(); abort(); }
          });
          res.once('aborted',refuse); res.once('error',refuse);
          res.once('end',() => { try { remaining(window); if (!res.complete || size !== Number(len) || res.trailers && Object.keys(res.trailers).length) return refuse(); metadata = parseControlMetadata(Buffer.concat(chunks,size)); ended = true; } catch { refuse(); abort(); } });
        });
        request.once('error',refuse);
        request.setTimeout(remaining(window),() => { refuse(); abort(); });
        request.end(body);
      });
      return await within(response,window);
    } finally { agent.destroy(); }
  } finally { window.signal.removeEventListener('abort',abort); abort(); }
}
export type ProtectedControlResult = Readonly<{available:true;metadata:Readonly<ControlMetadata>}> | Readonly<{available:false}>;
/** Sole production entry point. Captures wall+monotonic start before binding,
 * verified identity or request-body work. Client cancellation only closes this
 * connection; it never proves remote stop. No automatic replay is performed.
 */
export async function requestReplacementControl(request: Request): Promise<ProtectedControlResult> {
  const wall = Date.now(), mono = performance.now();
  const window: Window = {wall,mono,end:wall + 30000,signal:request.signal,proxyMonoEnd:process.hrtime.bigint()+30000000000n};
  try {
    const proxyWindow=readControlWindow(request.headers);
    window.end=Math.min(window.end,proxyWindow.wall_end);window.proxyMonoEnd=BigInt(proxyWindow.mono_end);
    const installed = readInstalledBinding();
    window.end = Math.min(window.end,instant(installed.profile.expires_at),instant(installed.profile.original_horizon));
    origin(request,installed.profile); remaining(window);
    await identity(installed.profile,window);
    const body = await readBody(request,window); const dto = validateControlRequest(body);
    const callerDeadline = instant(dto.caller_deadline);
    // Caller input narrows this original window; never mint, clamp or renew it.
    if (callerDeadline <= Date.now() || callerDeadline > wall + 30000 || callerDeadline > proxyWindow.wall_end || callerDeadline > instant(installed.profile.original_horizon) || callerDeadline > instant(installed.profile.expires_at)) return failure();
    window.end = Math.min(window.end,callerDeadline);
    current(installed,window); await identity(installed.profile,window); current(installed,window);
    const metadata = await transport(installed,body,window);
    if (dto.operation === 'reserve' ? metadata.populationSha256 !== dto.population_sha256 : metadata.runId !== dto.run_id) return failure();
    current(installed,window); await identity(installed.profile,window); current(installed,window);
    // The original deadline remains private in this invocation and the exact
    // request bytes. A later explicit identical request still needs every gate.
    return Object.freeze({available:true,metadata});
  } catch { return Object.freeze({available:false}); }
}
