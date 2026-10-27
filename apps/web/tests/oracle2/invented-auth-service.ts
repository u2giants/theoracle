/** Invented HTTPS Auth protocol fixture; no production imports are replaced. */
import assert from 'node:assert/strict';
import {createServer} from 'node:https';
import {createHmac,randomBytes} from 'node:crypto';
import {readFileSync} from 'node:fs';
export async function inventedAuthService(meta:{server_key_file:string;server_certificate_file:string;auth_user_id:string;auth_user_ids?:readonly string[]}){
 const key=randomBytes(32);const anon='invented-anon-'+randomBytes(16).toString('hex');
 const payload={sub:meta.auth_user_id,aud:'authenticated',role:'authenticated',exp:Math.floor(Date.now()/1000)+240,iat:Math.floor(Date.now()/1000)};
 const encode=(v:unknown)=>Buffer.from(JSON.stringify(v)).toString('base64url');
 const users=meta.auth_user_ids??[meta.auth_user_id];
 if(meta.auth_user_ids!==undefined){
  assert.ok(users.length===2&&users[0]===meta.auth_user_id&&new Set(users).size===2);
  assert.ok(users.every(user=>/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(user)));
 }
 const sessions=users.map(user=>{const unsigned=encode({alg:'HS256',typ:'JWT'})+'.'+encode({...payload,sub:user});return {user,token:unsigned+'.'+createHmac('sha256',key).update(unsigned).digest('base64url')};});
 const token=sessions[0]!.token;
 const state={mode:'valid' as 'valid'|'revoked'|'foreign',requests:0,accepted:0,rejected:0,foreignUser:'00000000-0000-4000-8000-000000000009',revokedUsers:new Set<string>(),acceptedUsers:[] as string[]};
 const server=createServer({key:readFileSync(meta.server_key_file),cert:readFileSync(meta.server_certificate_file),maxHeaderSize:8192},(req,res)=>{
  state.requests++;res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
  const session=sessions.find(candidate=>req.headers.authorization==='Bearer '+candidate.token);
  if(req.method!=='GET'||req.url!=='/auth/v1/user'||req.headers.apikey!==anon||!session||state.revokedUsers.has(session.user)||state.mode==='revoked'||Date.now()/1000>=payload.exp){state.rejected++;res.writeHead(401);res.end(JSON.stringify({code:'bad_jwt',message:'Invented session unavailable'}));return;}
  state.accepted++;state.acceptedUsers.push(session.user);res.writeHead(200);res.end(JSON.stringify({id:state.mode==='foreign'?state.foreignUser:session.user,aud:'authenticated',role:'authenticated',email:'invented-next@example.invalid',app_metadata:{provider:'magic_link_dev',providers:['magic_link_dev']},user_metadata:{},identities:[],created_at:new Date().toISOString()}));
 });
 server.requestTimeout=3000;server.headersTimeout=3000;server.keepAliveTimeout=1000;
 await new Promise<void>(r=>server.listen(0,'::1',r));const address=server.address();assert.ok(address&&typeof address!=='string');
 return {origin:'https://localhost.localdomain:'+address.port,anon,token,sessions:Object.freeze(sessions.map(session=>Object.freeze(session))),state,close:async()=>{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));assert.equal(server.listening,false);}};
}
