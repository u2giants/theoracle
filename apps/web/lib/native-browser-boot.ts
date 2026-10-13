// Start only the admitted invented-purpose server; never an unrestricted fallback.
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { loadSettings, currentNativeJob, protectedBytes } from './native-acceptance';
import { assertNativeEnvironment, assertNativeSettings, assertNativeDatabaseURL, readStaticManifest } from './native-browser-runtime.mjs';

async function main(){
  if(process.env.ORACLE2_PILOT_TOKEN!==undefined)throw Error();
  assertNativeEnvironment(process.env,false);
  process.env.ORACLE2_PILOT_TOKEN=protectedBytes('/run/oracle-native-browser/pilot-token',4096).toString('utf8').trim();
  assertNativeEnvironment(process.env);
  const c=loadSettings(Math.floor(Date.now()/1000));
  assertNativeSettings(process.env,c);
  let databaseBytes:Buffer|undefined;
  for(const key of ['database_url','database_ca','client_cert','client_key','server_ca','hmac_key'] as const){
    const pin=c[key];
    const bytes=protectedBytes(pin.path);
    if(realpathSync(pin.path)!==pin.path||createHash('sha256').update(bytes).digest('hex')!==pin.sha256)throw Error();
    if(key==='database_url')databaseBytes=bytes;
  }
  if(!databaseBytes)throw Error();
  assertNativeDatabaseURL(databaseBytes.toString('utf8').trim(),c);
  const manifest=readStaticManifest();
  if(manifest.source_revision!==process.env.ORACLE2_NATIVE_BROWSER_SOURCE_REVISION)throw Error();
  for(const asset of manifest.assets){
    const path=join('/app/apps/web/.next/static',asset.path.slice('/_next/static/'.length));
    if(createHash('sha256').update(readFileSync(path)).digest('hex')!==asset.sha256)throw Error();
  }
  // This admitted startup proves current exact read-only metadata identity,
  // actual SourceRefs/actor/release/lease, never provider or original access.
  await currentNativeJob(c,c.actor_id);
  const child=spawn(process.execPath,['/app/apps/web/server.js'],{stdio:'inherit',env:process.env});
  for(const signal of ['SIGINT','SIGTERM'] as const)process.on(signal,()=>child.kill(signal));
  child.on('error',()=>process.exit(1));
  child.on('exit',code=>process.exit(code??1));
}
main().catch(()=>{console.error('Native invented browser startup denied.');process.exit(1);});
