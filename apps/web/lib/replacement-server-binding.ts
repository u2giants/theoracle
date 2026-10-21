/** Node-only consumer of an independently installed appointment. Never issues one.
 * No framework `server-only` marker is installed; Node imports and runtime refusal
 * prevent browser use. Framework target verification remains a separate gate.
 */
import { constants, closeSync, fstatSync, lstatSync, openSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, parse, resolve } from 'node:path';
import { createHash, createPrivateKey, createPublicKey, X509Certificate } from 'node:crypto';

if (typeof window !== 'undefined') throw new Error('Replacement control unavailable');
const unavailable = (): never => { throw new Error('Replacement control unavailable'); };
export const sha256 = (value: Uint8Array | string): string => createHash('sha256').update(value).digest('hex');
const hash = /^[0-9a-f]{64}$/;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const exact = (v: unknown, fields: readonly string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k));
const text = (v: unknown, limit = 2048): v is string => typeof v === 'string' && v.length > 0 && v.length <= limit && v.trim() === v && !/[\u0000-\u001f\u007f]/.test(v);

/** Closed JSON parser. Duplicate names, invalid UTF-8, nonfinite numbers and
 * unpaired surrogates refuse before any DTO is used. ASCII wire field names
 * make canonical ordering identical to the Python requester's JSON encoding.
 */
export function parseClosedJson(bytes: Uint8Array, limit: number): unknown {
  if (bytes.length < 1 || bytes.length > limit) return unavailable();
  const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  let i = 0;
  const ws = () => { while (/[\x20\t\r\n]/.test(raw[i] ?? '') && i < raw.length) i++; };
  const string = (): string => {
    const start = i++;
    while (i < raw.length) {
      const c = raw[i++];
      if (c === '\\') { i++; continue; }
      if (c === '"') {
        const value: unknown = JSON.parse(raw.slice(start, i));
        if (typeof value !== 'string' || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) return unavailable();
        return value;
      }
    }
    return unavailable();
  };
  const value = (depth: number): unknown => {
    if (depth > 10) return unavailable();
    ws(); const c = raw[i];
    if (c === '"') return string();
    if (c === '{') {
      i++; ws(); const result: Record<string, unknown> = Object.create(null);
      if (raw[i] === '}') { i++; return result; }
      for (;;) {
        ws(); if (raw[i] !== '"') return unavailable();
        const key = string(); if (Object.hasOwn(result, key)) return unavailable();
        ws(); if (raw[i++] !== ':') return unavailable();
        result[key] = value(depth + 1); ws();
        const end = raw[i++]; if (end === '}') return result;
        if (end !== ',') return unavailable();
      }
    }
    if (c === '[') {
      i++; ws(); const result: unknown[] = [];
      if (raw[i] === ']') { i++; return result; }
      for (;;) {
        if (result.length >= 1000) return unavailable();
        result.push(value(depth + 1)); ws();
        const end = raw[i++]; if (end === ']') return result;
        if (end !== ',') return unavailable();
      }
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(raw.slice(i))?.[0];
    if (!token) return unavailable();
    i += token.length; const out: unknown = JSON.parse(token);
    if (typeof out === 'number' && (!Number.isSafeInteger(out) || Object.is(out, -0))) return unavailable();
    return out;
  };
  const out = value(0); ws(); if (i !== raw.length) return unavailable();
  return out;
}
export function canonicalJson(v: unknown): string {
  if (v === null || typeof v === 'boolean' || typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'number' && Number.isSafeInteger(v) && !Object.is(v, -0)) return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(canonicalJson).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonicalJson((v as Record<string, unknown>)[k])).join(',') + '}';
  return unavailable();
}
export const canonicalUuid = (v: unknown): v is string => typeof v === 'string' && uuid.test(v);
export const canonicalHash = (v: unknown): v is string => typeof v === 'string' && hash.test(v);
export function instant(v: unknown): number {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(v)) return unavailable();
  const ms = Date.parse(v); if (!Number.isFinite(ms)) return unavailable();
  // Date.parse normalizes nonexistent dates. Reject these before accepting a window.
  const date = v.slice(0, 10), day = Number(date.slice(8)), month = Number(date.slice(5, 7)), year = Number(date.slice(0, 4));
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate() || Number(v.slice(11, 13)) > 23 || Number(v.slice(14, 16)) > 59 || Number(v.slice(17, 19)) > 59) return unavailable();
  const fraction = /\.(\d+)/.exec(v)?.[1] ?? '';
  return ms + Number(fraction.padEnd(6, '0').slice(3, 6)) / 1000;
}

export interface ServerBinding {
  readonly schema_version: 1;
  readonly purpose: 'replacement-web-binding-v1';
  readonly project_url: string; readonly auth_issuer: string;
  readonly auth_user_id: string; readonly employee_id: string;
  readonly principal_id: string; readonly workspace_id: string;
  readonly runtime_hash: string; readonly registry_hash: string;
  readonly intake_appointment_sha256: string; readonly peer_profile_sha256: string;
  readonly web_origin: string; readonly backend_origin: string;
  readonly control_path: '/v1/replacement/control'; readonly server_dns: string;
  readonly server_certificate_der_sha256: string;
  readonly server_ca_file: string; readonly server_ca_sha256: string;
  readonly client_certificate_file: string; readonly client_certificate_sha256: string;
  readonly client_certificate_der_sha256: string; readonly client_uri: string;
  readonly client_key_file: string; readonly client_key_sha256: string;
  readonly issuer_actor: string; readonly reviewer_actor: string;
  readonly valid_from: string; readonly expires_at: string; readonly original_horizon: string;
}
const fields = ['schema_version','purpose','project_url','auth_issuer','auth_user_id','employee_id','principal_id','workspace_id','runtime_hash','registry_hash','intake_appointment_sha256','peer_profile_sha256','web_origin','backend_origin','control_path','server_dns','server_certificate_der_sha256','server_ca_file','server_ca_sha256','client_certificate_file','client_certificate_sha256','client_certificate_der_sha256','client_uri','client_key_file','client_key_sha256','issuer_actor','reviewer_actor','valid_from','expires_at','original_horizon'] as const;
const httpsOrigin = (v: unknown): v is string => {
  if (!text(v)) return false;
  try { const u = new URL(v); return u.protocol === 'https:' && !u.username && !u.password && u.origin === v; } catch { return false; }
};
/** Descriptive validation alone is never installation, admission or permission. */
export function validateBinding(v: unknown): Readonly<ServerBinding> {
  if (!exact(v, fields) || v.schema_version !== 1 || v.purpose !== 'replacement-web-binding-v1') return unavailable();
  for (const k of ['auth_user_id','employee_id','principal_id','workspace_id'] as const) if (!canonicalUuid(v[k])) return unavailable();
  for (const k of ['runtime_hash','registry_hash','intake_appointment_sha256','peer_profile_sha256','server_certificate_der_sha256','server_ca_sha256','client_certificate_sha256','client_certificate_der_sha256','client_key_sha256'] as const) if (!canonicalHash(v[k])) return unavailable();
  if (!httpsOrigin(v.project_url) || v.auth_issuer !== v.project_url + '/auth/v1' || !httpsOrigin(v.web_origin) || !httpsOrigin(v.backend_origin) || v.control_path !== '/v1/replacement/control') return unavailable();
  if (!text(v.server_dns, 253) || !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(v.server_dns) || new URL(v.backend_origin).hostname !== v.server_dns || !v.server_dns.includes('.') || v.server_dns.includes('..')) return unavailable();
  if (!text(v.client_uri, 256) || !/^spiffe:\/\/oracle\/[a-zA-Z0-9/_-]+$/.test(v.client_uri)) return unavailable();
  for (const k of ['server_ca_file','client_certificate_file','client_key_file'] as const) if (!text(v[k]) || !isAbsolute(v[k]) || resolve(v[k]) !== v[k]) return unavailable();
  if (v.server_ca_file === v.client_key_file || v.server_ca_file === v.client_certificate_file || v.client_key_file === v.client_certificate_file) return unavailable();
  if (!text(v.issuer_actor, 160) || !text(v.reviewer_actor, 160) || v.issuer_actor === v.reviewer_actor || v.issuer_actor === v.principal_id || v.reviewer_actor === v.principal_id) return unavailable();
  const from = instant(v.valid_from), expires = instant(v.expires_at), horizon = instant(v.original_horizon);
  if (!(from < expires && expires <= horizon)) return unavailable();
  return Object.freeze(v) as unknown as Readonly<ServerBinding>;
}

export interface IdentitySnapshot { readonly configuredProjectUrl: string; readonly actualProjectUrl: string; readonly verifiedUserId: string; readonly employeeId: string; readonly disabledAt: unknown; }
/** Pure descriptive unit helper; production cannot inject this snapshot. */
export function matchesIdentity(binding: Readonly<ServerBinding>, snapshot: IdentitySnapshot): boolean {
  return snapshot.configuredProjectUrl === binding.project_url && snapshot.actualProjectUrl === binding.project_url && binding.auth_issuer === snapshot.actualProjectUrl + '/auth/v1' && snapshot.verifiedUserId === binding.auth_user_id && snapshot.employeeId === binding.employee_id && snapshot.disabledAt === null;
}

interface PinnedFile { readonly path: string; readonly digest: string; readonly identity: string; readonly bytes: Buffer; }
function protectedRead(path: string, expected: string): PinnedFile {
  if (!isAbsolute(path) || resolve(path) !== path || !hash.test(expected)) return unavailable();
  const parents = (): string => {
    let ancestor = dirname(path); const identities: string[] = [];
    for (;;) {
      const stat = lstatSync(ancestor);
      if (!stat.isDirectory() || stat.isSymbolicLink()) return unavailable();
      identities.push([ancestor,stat.dev,stat.ino,stat.mode,stat.uid].join(':'));
      if (ancestor === parse(ancestor).root) break; ancestor = dirname(ancestor);
    }
    return identities.join('|');
  };
  const parentIdentity = parents();
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const a = fstatSync(fd);
    if (!a.isFile() || a.nlink !== 1 || (a.mode & 0o077) !== 0 || a.uid !== process.getuid?.() || a.size < 1 || a.size > 65536) return unavailable();
    const bytes = readFileSync(fd); const b = fstatSync(fd), current = lstatSync(path);
    const identity = (s: typeof a) => [s.dev,s.ino,s.mode,s.uid,s.nlink,s.size,s.ctimeMs,s.mtimeMs].join(':');
    if (parentIdentity !== parents() || identity(a) !== identity(b) || identity(a) !== identity(current) || sha256(bytes) !== expected) return unavailable();
    return { path, digest: expected, identity: parentIdentity + '|' + identity(a), bytes };
  } finally { closeSync(fd); }
}
let installed: { readonly path: string; readonly digest: string; readonly identity: string; readonly profile: Readonly<ServerBinding>; readonly files: readonly PinnedFile[] } | undefined;
export interface InstalledBinding { readonly profile: Readonly<ServerBinding>; readonly ca: Buffer; readonly cert: Buffer; readonly key: Buffer; }
/** Configuration selectors are read only from server configuration, once per instance.
 * File identity changes refuse even when the replacement has identical bytes.
 * The appointment/peer hashes require independent backend installation; this
 * consumer cannot prove their relationship merely by reading a supplied hash.
 */
function loadInstalledBinding(): InstalledBinding {
  const path = process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE;
  const digest = process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256;
  if (!path || !digest || (installed && (path !== installed.path || digest !== installed.digest))) return unavailable();
  const pinned = protectedRead(path, digest);
  const profile = validateBinding(parseClosedJson(pinned.bytes, 16384));
  const now = Date.now();
  if (now < instant(profile.valid_from) || now >= instant(profile.expires_at) || now >= instant(profile.original_horizon)) return unavailable();
  const files = [protectedRead(profile.server_ca_file,profile.server_ca_sha256),protectedRead(profile.client_certificate_file,profile.client_certificate_sha256),protectedRead(profile.client_key_file,profile.client_key_sha256)];
  if (installed && (installed.identity !== pinned.identity || files.some((f,i) => f.identity !== installed!.files[i]!.identity || f.path !== installed!.files[i]!.path || f.digest !== installed!.files[i]!.digest))) return unavailable();
  const cert = new X509Certificate(files[1]!.bytes);
  if (sha256(cert.raw) !== profile.client_certificate_der_sha256 || !cert.subjectAltName?.split(', ').includes('URI:' + profile.client_uri) || now < Date.parse(cert.validFrom) || now >= Date.parse(cert.validTo)) return unavailable();
  const key = createPrivateKey(files[2]!.bytes);
  if (!cert.checkPrivateKey(key) || !createPublicKey(key).equals(cert.publicKey)) return unavailable();
  installed ??= { path,digest,identity:pinned.identity,profile,files };
  return { profile: installed.profile, ca: files[0]!.bytes,cert:files[1]!.bytes,key:files[2]!.bytes };
}

/** Fail closed without exposing protected paths or key/parser diagnostics. */
export function readInstalledBinding(): InstalledBinding {
  try { return loadInstalledBinding(); } catch { return unavailable(); }
}
