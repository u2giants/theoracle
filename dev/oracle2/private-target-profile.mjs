// Owner: Oracle coordinator (#27). One metadata resolver for worker/MCP routing.
// Required for public-boundary privacy without losing exact routing; retire only
// after a reviewed successor preserves all pinned targets and private custody.
// This file neither loads credentials nor grants authority.
import { createHash } from 'node:crypto';
import { constants, openSync, closeSync, fstatSync, readFileSync, lstatSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, isAbsolute } from 'node:path';
import { execFileSync } from 'node:child_process';
import registry from './public-target-pins.json' with { type: 'json' };

const EXPECTED_KEYS = ['coolify_api_base_url','legacy_trigger_project','native_supabase_project','native_trigger_project','oracle_supabase_project'];
if (registry.schema_version !== 1 || Object.keys(registry.targets ?? {}).sort().join('|') !== EXPECTED_KEYS.join('|'))
  throw new Error('Public target commitment registry unavailable');
const TARGETS = Object.freeze({ ...registry.targets });
const HASH = /^[a-f0-9]{64}$/;
const fail = () => { throw new Error('Private target metadata unavailable'); };
export const defaultTargetProfile = () => {
  if (Object.hasOwn(process.env, 'ORACLE_TARGET_PROFILE_PATH')) {
    const path = process.env.ORACLE_TARGET_PROFILE_PATH;
    if (!path || !isAbsolute(path)) fail();
    return path;
  }
  return join(homedir(), '.config', 'oracle', 'targets.json');
};
export const targetPins = () => Object.freeze({ ...TARGETS });
export function isPinnedTarget(key, value) {
  return Object.hasOwn(TARGETS, key) && typeof value === 'string'
    && createHash('sha256').update(value, 'utf8').digest('hex') === TARGETS[key];
}
export function assertPinnedTarget(key, value) {
  if (!isPinnedTarget(key, value)) fail();
  return value;
}
// Pure schema/protocol validator; routing always supplies this module's pinned registry.
export function validateTargetDocument(value, pins = TARGETS) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).sort().join('|') !== 'schema_version|targets'
      || value.schema_version !== 1 || !value.targets || typeof value.targets !== 'object'
      || Array.isArray(value.targets)
      || Object.keys(value.targets).sort().join('|') !== Object.keys(pins).sort().join('|')) fail();
  for (const [key, pin] of Object.entries(pins)) {
    const v = value.targets[key];
    let validFormat = false;
    if (typeof v === 'string') {
      if (key === 'coolify_api_base_url') {
        try { const u = new URL(v); validFormat = ['http:','https:'].includes(u.protocol)
          && !!u.hostname && !u.username && !u.password && !u.search && !u.hash && u.pathname === '/api/v1'; } catch {}
      } else validFormat = (key.endsWith('_trigger_project') ? /^proj_[a-z]{20}$/ : /^[a-z]{20}$/).test(v);
    }
    if (typeof pin !== 'string' || !HASH.test(pin) || !validFormat
        || createHash('sha256').update(v, 'utf8').digest('hex') !== pin) fail();
  }
  return Object.freeze({ ...value.targets });
}
function privateWindowsAcl(path) {
  // No credentials are forwarded to the read-only ACL inspector.
  const env = Object.fromEntries(['PATH','SystemRoot','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE']
    .flatMap(k => process.env[k] === undefined ? [] : [[k, process.env[k]]]));
  env.ORACLE_METADATA_PROFILE = path;
  const script = "$ErrorActionPreference='Stop';$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;$ok=@($sid,'S-1-5-18','S-1-5-32-544');foreach($p in @($env:ORACLE_METADATA_PROFILE,(Split-Path -Parent $env:ORACLE_METADATA_PROFILE))){$i=Get-Item -LiteralPath $p -Force;if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){exit 1};$a=Get-Acl -LiteralPath $p;if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid){exit 1};foreach($r in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Value -notin $ok){exit 1}}};exit 0";
  execFileSync('pwsh', ['-NoProfile','-NonInteractive','-Command',script],
    { env, stdio: ['ignore','pipe','ignore'], timeout: 10000 });
}
export function readBoundedTargetJson(path, { privateProfile = false } = {}) {
  if (typeof path !== 'string' || !isAbsolute(path)) fail();
  let fd;
  try {
    if (privateProfile) {
      const parent = lstatSync(dirname(path));
      if (!parent.isDirectory() || parent.isSymbolicLink()) fail();
      if (process.platform === 'win32') privateWindowsAcl(path);
      else if (parent.uid !== process.getuid() || (parent.mode & 0o077)) fail();
    }
    fd = openSync(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0) | (constants.O_NONBLOCK ?? 0));
    const st = fstatSync(fd);
    if (!st.isFile() || st.nlink !== 1 || st.size < 2 || st.size > (privateProfile ? 16384 : 1048576)) fail();
    if (privateProfile && process.platform !== 'win32'
        && (st.uid !== process.getuid() || (st.mode & 0o077))) fail();
    const value = JSON.parse(readFileSync(fd, 'utf8'));
    const after = fstatSync(fd);
    if (after.dev !== st.dev || after.ino !== st.ino || after.size !== st.size
        || after.mtimeMs !== st.mtimeMs || after.ctimeMs !== st.ctimeMs) fail();
    return value;
  } catch { fail(); }
  finally { if (fd !== undefined) closeSync(fd); }
}
export function readPrivateTarget(key, profilePath = defaultTargetProfile()) {
  const profile = validateTargetDocument(readBoundedTargetJson(profilePath, { privateProfile: true }));
  return assertPinnedTarget(key, profile[key]);
}
export function resolveNativeTriggerProject(env = process.env, { allowDefault = true } = {}) {
  try {
    const custom = env.ORACLE2_NATIVE_TRIGGER_PROJECT_REF;
    const official = env.TRIGGER_PROJECT_REF;
    if (custom !== undefined && official !== undefined && custom !== official) fail();
    const explicit = custom ?? official;
    if (explicit !== undefined) assertPinnedTarget('native_trigger_project', explicit);
    let indexed;
    if (allowDefault && env.TRIGGER_BUILD_MANIFEST_PATH !== undefined) {
      const manifest = readBoundedTargetJson(env.TRIGGER_BUILD_MANIFEST_PATH);
      indexed = assertPinnedTarget('native_trigger_project', manifest?.config?.project);
      if (explicit !== undefined && explicit !== indexed) fail();
    }
    const value = explicit ?? indexed ?? (allowDefault ? readPrivateTarget('native_trigger_project') : undefined);
    return assertPinnedTarget('native_trigger_project', value);
  } catch { throw new Error('Exact dedicated isolated native proof project required'); }
}
