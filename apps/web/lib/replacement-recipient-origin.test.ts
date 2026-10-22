/** Invented protected JSON only. Static restriction must not touch keys or auth. */
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,writeFileSync,rmSync,unlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {canonicalJson,sha256} from './replacement-server-binding';
const uid='11111111-1111-4111-8111-111111111111',employee='22222222-2222-4222-8222-222222222222';
const project='https://invented-auth.example.test',origin='https://invented-web.example.test',hash='a'.repeat(64);
let serial=0;
async function owner(){return import(new URL('../../../packages/shared/src/protected-server-binding.ts?static-origin-'+serial++,import.meta.url).href);}
function fixture(variant='valid',purpose:'control'|'recommendation'='control'){
 const dir=mkdtempSync(join(tmpdir(),'oracle-static-origin-')),now=Date.now(),end=now+60000,profileEnd=variant==='short-profile'?now+3000:end;
 const profile:Record<string,unknown>={schema_version:1,purpose:'replacement-web-binding-v1',project_url:project,auth_issuer:project+'/auth/v1',auth_user_id:uid,employee_id:employee,principal_id:'33333333-3333-4333-8333-333333333333',workspace_id:'44444444-4444-4444-8444-444444444444',runtime_hash:hash,registry_hash:hash,intake_appointment_sha256:hash,peer_profile_sha256:hash,web_origin:origin,backend_origin:'https://backend.example.test',control_path:'/v1/replacement/control',server_dns:'backend.example.test',server_certificate_der_sha256:hash,server_ca_file:join(dir,'ABSENT-CA'),server_ca_sha256:hash,client_certificate_file:join(dir,'ABSENT-CERT'),client_certificate_sha256:hash,client_certificate_der_sha256:hash,client_uri:'spiffe://oracle/invented-static',client_key_file:join(dir,'ABSENT-KEY'),client_key_sha256:hash,issuer_actor:'invented-issuer',reviewer_actor:'invented-reviewer',valid_from:new Date(now-1000).toISOString(),expires_at:new Date(profileEnd).toISOString(),original_horizon:new Date(profileEnd).toISOString()};
 if(purpose==='recommendation'){profile.purpose='replacement-recommendation-actions-web-binding-v1';profile.recommendation_path='/v1/replacement/recommendation-actions';profile.model_id=uid;profile.recommendation_config_sha256=hash;profile.recommendation_peer_profile_sha256=hash;for(const key of ['intake_appointment_sha256','peer_profile_sha256','control_path'])Reflect.deleteProperty(profile,key);}
 if(variant==='foreign-user')profile.auth_user_id=employee;
 if(variant==='foreign-employee')profile.employee_id=uid;
 if(variant==='foreign-issuer')profile.auth_issuer='https://foreign.example.test/auth/v1';
 if(variant==='wrong-purpose')profile.purpose='replacement-upload-web-binding-v1';
 if(variant==='unknown-field')profile.authority=true;
 if(variant==='expired-profile')profile.expires_at=new Date(now-1).toISOString();
 if(variant==='future-profile')profile.valid_from=new Date(now+1000).toISOString();
 if(variant==='profile-horizon')profile.original_horizon=new Date(end+1).toISOString();
 const profilePath=join(dir,'profile.json'),bytes=variant==='noncanonical-profile'?JSON.stringify(profile,null,2):canonicalJson(profile);
 writeFileSync(profilePath,bytes,{mode:0o600});if(variant==='missing-profile')unlinkSync(profilePath);
 const entry={project_url:project,auth_issuer:project+'/auth/v1',auth_user_id:uid,employee_id:employee,bindings:{[purpose]:{path:profilePath,sha256:variant==='wrong-pin'?'b'.repeat(64):sha256(bytes)}}};
 const index={schema_version:1,purpose:'replacement-employee-recipient-index-v1',issuer_actor:'55555555-5555-4555-8555-555555555555',reviewer_actor:'66666666-6666-4666-8666-666666666666',valid_from:new Date(now-1000).toISOString(),expires_at:new Date(variant==='expired-index'?now-1:end).toISOString(),original_horizon:new Date(end).toISOString(),recipients:[entry]};
 const path=join(dir,'index.json');writeFileSync(path,canonicalJson(index),{mode:0o600});
 const previous=[process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE,process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256];
 process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE=path;process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256=sha256(canonicalJson(index));
 return {dir,end,profileEnd,profilePath,index,indexPath:path,cleanup(){for(const [n,v]of [['ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE',previous[0]],['ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256',previous[1]]] as const){if(v===undefined)delete process.env[n];else process.env[n]=v;}rmSync(dir,{recursive:true,force:true});}};
}
for(const variant of ['missing-profile','foreign-user','foreign-employee','foreign-issuer','wrong-purpose','unknown-field','expired-profile','future-profile','profile-horizon','noncanonical-profile','wrong-pin','expired-index'])test('static origin rejects '+variant,async()=>{
 const f=fixture(variant);try{const m=await owner();assert.throws(()=>m.admitEmployeeRecipientOriginV1('control',project,origin,origin+'/path'));}finally{f.cleanup();}
});
test('static restriction reads profile only, returns no identity and never renews absolute horizon',async()=>{
 const f=fixture();try{
  const m=await owner(),a=m.admitEmployeeRecipientOriginV1('control',project,origin,origin+'/path');
  assert.deepEqual(a,{origin,validUntil:f.end});assert.equal(Object.isFrozen(a),true);
  assert.deepEqual(m.admitEmployeeRecipientOriginV1('control',project,origin,origin+'/other'),a);
  for(const args of [['control',project,'https://foreign.example.test',origin],['control',project,origin,'https://foreign.example.test/path'],['control','https://foreign.example.test',origin,origin],['viewer',project,origin,origin],['control',project,null,origin]] as const)assert.throws(()=>m.admitEmployeeRecipientOriginV1(...args));
  writeFileSync(f.profilePath,'{}');assert.throws(()=>m.admitEmployeeRecipientOriginV1('control',project,origin,origin));
 }finally{f.cleanup();}
});

test('matching profiles alone conservatively narrow longer index horizon',async()=>{
 const f=fixture('short-profile');try{
  const initial=JSON.parse((await import('node:fs')).readFileSync(f.profilePath,'utf8'));
  for(const [suffix,web,lease]of [['matched',origin,2000],['unmatched','https://other-web.example.test',1000]] as const){
   const path=join(f.dir,suffix+'.json'),at=Date.now()+lease,auth=suffix==='matched'?'77777777-7777-4777-8777-777777777777':'88888888-8888-4888-8888-888888888888';
   const profile={...initial,auth_user_id:auth,web_origin:web,expires_at:new Date(at).toISOString(),original_horizon:new Date(at).toISOString()};
   writeFileSync(path,canonicalJson(profile),{mode:0o600});f.index.recipients.push({...f.index.recipients[0]!,auth_user_id:auth,bindings:{control:{path,sha256:sha256(canonicalJson(profile))}}});
  }
  writeFileSync(f.indexPath,canonicalJson(f.index));process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256=sha256(canonicalJson(f.index));
  const m=await owner(),restriction=m.admitEmployeeRecipientOriginV1('control',project,origin,origin+'/path');
  const matched=JSON.parse((await import('node:fs')).readFileSync(join(f.dir,'matched.json'),'utf8'));
  assert.equal(restriction.validUntil,Date.parse(matched.expires_at));assert.ok(restriction.validUntil<f.profileEnd&&restriction.validUntil<f.end);
 }finally{f.cleanup();}
});

for(const variant of ['missing-profile','foreign-user','foreign-employee','foreign-issuer','wrong-purpose','unknown-field','expired-profile','future-profile','profile-horizon','noncanonical-profile','wrong-pin','expired-index'])test('recommendation static origin refuses before auth/key access: '+variant,async()=>{
 const f=fixture(variant,'recommendation');try{const m=await owner();assert.throws(()=>m.admitEmployeeRecipientOriginV1('recommendation',project,origin,origin+'/advice'));}finally{f.cleanup();}
});
test('recommendation profile short lease narrows index and rejects foreign origin without key reads',async()=>{
 const f=fixture('short-profile','recommendation');try{const m=await owner();assert.deepEqual(m.admitEmployeeRecipientOriginV1('recommendation',project,origin,origin+'/advice'),{origin,validUntil:f.profileEnd});for(const value of [null,'https://foreign.example.test'])assert.throws(()=>m.admitEmployeeRecipientOriginV1('recommendation',project,value,origin+'/advice'));writeFileSync(f.profilePath,'{}');assert.throws(()=>m.admitEmployeeRecipientOriginV1('recommendation',project,origin,origin+'/advice'));}finally{f.cleanup();}
});
test('recipient index accepts all nine exact purposes and rejects alias or tenth purpose',async()=>{
 const f=fixture('valid','recommendation');try{const m=await owner(),purposes=['control','viewer','upload','review','conversation','meeting','answer','mcp-answer','recommendation'];const bindings=Object.fromEntries(purposes.map((kind,n)=>[kind,{path:join(f.dir,'purpose-'+n+'.json'),sha256:hash}]));const index={...f.index,recipients:[{...f.index.recipients[0],bindings}]};assert.equal(Object.keys(m.validateEmployeeRecipientIndexV1(index).recipients[0]!.bindings).length,9);for(const kind of ['recommendation-actions','admin']){const changed=structuredClone(index);changed.recipients[0]!.bindings[kind]={path:join(f.dir,kind+'.json'),sha256:hash};assert.throws(()=>m.validateEmployeeRecipientIndexV1(changed));}}finally{f.cleanup();}
});
