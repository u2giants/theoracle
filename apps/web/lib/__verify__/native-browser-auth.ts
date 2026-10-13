import assert from 'node:assert/strict';
import { nativeSessions,nativeCookie,NATIVE_COOKIE,NATIVE_COOKIE_PATH } from '../native-browser-auth';
import { authorizePilotRequest } from '../oracle2-pilot-auth';
import type { NativeSettings } from '../native-acceptance';
let now=1000,token='public-invented-existing-issuer-fixture',allow=true,live=true,currentCalls=0;
const c={purpose:'public-invented-native-browser',actor_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
 job_expires_at:2000,source_authority_expires_at:2000,worker_permit_expires_at:2000} as NativeSettings;
const auth=nativeSessions({token:()=>token,actors:()=>new Set(allow?[c.actor_id]:[]),settings:()=>c,identity:()=>{},
 current:async()=>{currentCalls++;if(!live)throw Error('revoked');return {expiresAt:2000};},clock:()=>now});
let checks=0;
const wrong=await auth.create('wrong');assert.equal(wrong.ok,false);assert.equal(currentCalls,0);checks++;
const issued=await auth.create(token);assert.equal(issued.ok,true);checks++;
if(!issued.ok)throw Error();
const headers=new Headers({cookie:NATIVE_COOKIE+'='+issued.sessionId});
assert.equal((await auth.authorize(headers)).ok,true);checks++;
assert.match(nativeCookie(issued.sessionId),/HttpOnly; Secure; SameSite=Strict; Max-Age=300/);checks++;
assert.ok(nativeCookie(issued.sessionId).includes('Path='+NATIVE_COOKIE_PATH));checks++;
assert.equal((await authorizePilotRequest(headers)).ok,false);checks++;
assert.equal((await auth.authorize(new Headers({cookie:'oracle2_pilot_session='+issued.sessionId}))).ok,false);checks++;
assert.equal((await auth.authorize(new Headers({cookie:NATIVE_COOKIE+'='+issued.sessionId+'; '+NATIVE_COOKIE+'='+issued.sessionId}))).ok,false);checks++;
now=1300;assert.equal((await auth.authorize(headers)).ok,false);checks++;
now=1000;const another=await auth.create(token);if(!another.ok)throw Error();
live=false;assert.equal((await auth.authorize(new Headers({cookie:NATIVE_COOKIE+'='+another.sessionId}))).ok,false);checks++;
live=true;allow=false;assert.equal((await auth.create(token)).ok,false);checks++;
allow=true;const last=await auth.create(token);if(!last.ok)throw Error();token='different-public-issuer-fixture';
assert.equal((await auth.authorize(new Headers({cookie:NATIVE_COOKIE+'='+last.sessionId}))).ok,false);checks++;
const raced=nativeSessions({token:()=>token,actors:()=>new Set([c.actor_id]),settings:()=>c,identity:()=>{},
 current:async()=>{token='replacement-public-fixture';return {expiresAt:2000};},clock:()=>now});
assert.equal((await raced.create(token)).ok,false);checks++;
console.log(`native purpose session verification: ${checks} passed; invented fixtures only; live acceptance false`);
