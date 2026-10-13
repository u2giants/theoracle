// Fixed purpose-only companion boundary. No caller-selected routes or targets.
import { readFileSync } from 'node:fs';

export const STATIC_MANIFEST='/app/native-browser-static.json';
const ALLOWED_SECRET_ENV=new Set(['ORACLE2_PILOT_TOKEN']);
const FORBIDDEN=/(SUPABASE|OPENAI|OPENROUTER|ANTHROPIC|VERTEX|GEMINI|GOOGLE|TRIGGER|RECALL|CLOUDFLARE|AWS_|AZURE_|ADMIN|DATABASE_URL|DB_URL|API_KEY|PRIVATE_KEY|SECRET|TOKEN)/i;

export function assertNativeEnvironment(env, requireToken=true){
  if(env.NODE_VERSION!==undefined&&env.NODE_VERSION!=='24.21.0')throw Error('Native browser unavailable');
  if(env.ORACLE2_NATIVE_BROWSER_ONLY!=='1'||env.NODE_ENV!=='production')throw Error('Native browser unavailable');
  const allowed=new Set(['PATH','HOME','NODE_VERSION','YARN_VERSION','HOSTNAME','LANG','LC_ALL','TZ','TERM','NODE_ENV','PORT','HOSTNAME','ORACLE2_PILOT_TOKEN','ORACLE2_PILOT_WORKSPACE_ID','ORACLE2_PILOT_ACTOR','ORACLE2_PILOT_ACTORS','ORACLE2_NATIVE_BROWSER_ONLY','ORACLE2_NATIVE_BROWSER_PUBLIC_HOST','ORACLE2_NATIVE_BROWSER_SOURCE_REVISION','ORACLE2_NATIVE_ACCEPTANCE_SETTINGS','ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256']);
  // These keys are created by the pinned Next standalone server after sealed
  // bootstrap. Caller-supplied values remain denied by the pre-token check.
  if(requireToken)for(const key of ['__NEXT_PRIVATE_STANDALONE_CONFIG','__NEXT_PRIVATE_ORIGIN','NEXT_DEPLOYMENT_ID','TURBOPACK'])allowed.add(key);
  for(const key of Object.keys(env))if(!allowed.has(key))throw Error('Native browser unavailable');
  for(const key of Object.keys(env))if((FORBIDDEN.test(key)&&!ALLOWED_SECRET_ENV.has(key))||['NODE_OPTIONS','NODE_PATH'].includes(key))throw Error('Native browser unavailable');
  if((requireToken&&!env.ORACLE2_PILOT_TOKEN)||!env.ORACLE2_PILOT_WORKSPACE_ID
    ||!env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS||!/^[a-f0-9]{64}$/.test(env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256??'')
    ||!env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST||!env.ORACLE2_NATIVE_BROWSER_SOURCE_REVISION
    ||!/^[a-f0-9]{40}$/.test(env.ORACLE2_NATIVE_BROWSER_SOURCE_REVISION)
    ||env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS!=='/run/oracle-native-browser/settings.json')throw Error('Native browser unavailable');
  const host=env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST;
  if(!/^[a-z0-9][a-z0-9.-]{1,250}[a-z0-9]$/.test(host)||host.includes('..')
    ||host==='oracle.designflow.app'||host==='oracle.designflow.app:443')throw Error('Native browser unavailable');
}

export function assertNativeSettings(env,c){
  assertNativeEnvironment(env);
  if(env.ORACLE2_PILOT_ACTOR!==undefined&&env.ORACLE2_PILOT_ACTORS!==undefined)throw Error('Native browser unavailable');
  const actors=(env.ORACLE2_PILOT_ACTOR??env.ORACLE2_PILOT_ACTORS??'').split(',').map(value=>value.trim());
  if(actors.length!==1||actors[0]!==c.actor_id||env.ORACLE2_PILOT_WORKSPACE_ID!==c.workspace_id
    ||c.purpose!=='public-invented-native-browser'||c.hostname!=='gateway'||c.origin!=='https://gateway:8443'
    ||c.public_page_origin!==`https://${env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST}`
    ||c.metadata_role!=='oracle2_gateway_metadata'||!c.metadata_login)throw Error('Native browser unavailable');
  const paths={database_url:'database-url',database_ca:'ledger-ca.crt',client_cert:'client.crt',
    client_key:'client.key',server_ca:'gateway-ca.crt',hmac_key:'hmac-key'};
  for(const [key,name] of Object.entries(paths))if(c[key]?.path!==`/run/oracle-native-browser/${name}`)throw Error('Native browser unavailable');
}

export function readStaticManifest(path=STATIC_MANIFEST){
  const manifest=JSON.parse(readFileSync(path,'utf8'));
  if(manifest.schema_version!==1||!Array.isArray(manifest.assets)||!manifest.assets.length
    ||!/^[a-f0-9]{40}$/.test(manifest.source_revision))throw Error('Native browser unavailable');
  const seen=new Set();
  for(const asset of manifest.assets){
    if(!asset||typeof asset.path!=='string'||!asset.path.startsWith('/_next/static/')||asset.path.includes('..')
      ||asset.path.includes('%')||!/^[a-f0-9]{64}$/.test(asset.sha256)||seen.has(asset.path))throw Error('Native browser unavailable');
    seen.add(asset.path);
  }
  return manifest;
}

export function nativeRequestAllowed(url,method,host,env,manifest){
  assertNativeEnvironment(env);
  if(manifest.source_revision!==env.ORACLE2_NATIVE_BROWSER_SOURCE_REVISION)throw Error('Native browser unavailable');
  if(host!==env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST)return false;
  const target=new URL(url);
  if(target.username||target.password||target.pathname.includes('%')||target.pathname.includes('\\'))return false;
  if(target.pathname==='/consultant/native-acceptance')return ['GET','HEAD'].includes(method);
  if(target.pathname==='/api/consultant/native-acceptance/source')return method==='GET'&&!target.search;
  if(target.pathname==='/api/consultant/native-acceptance')return !target.search&&['GET','POST'].includes(method);
  if(target.pathname==='/api/consultant/native-acceptance/session')return !target.search&&['POST','DELETE'].includes(method);
  return ['GET','HEAD'].includes(method)&&manifest.assets.some(asset=>asset.path===target.pathname);
}

export function nativeForwardingAllowed(host,proto,forwardedHost,forwarded,env){
  assertNativeEnvironment(env);
  return host===env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST&&proto==='https'
    &&(forwardedHost===null||forwardedHost===host)&&forwarded===null;
}

export function assertNativeDatabaseURL(raw,c){
  const url=new URL(raw);
  const keys=[...url.searchParams.keys()].sort();
  if(!['postgres:','postgresql:'].includes(url.protocol)||url.hostname!=='ledger'
    ||!['','5432'].includes(url.port)||url.pathname!=='/oracle_synthetic'||url.hash
    ||decodeURIComponent(url.username)!==c.metadata_login
    ||keys.join('|')!=='sslmode|sslrootcert'||url.searchParams.get('sslmode')!=='verify-full'
    ||url.searchParams.get('sslrootcert')!==c.database_ca.path)throw Error('Native browser unavailable');
}
