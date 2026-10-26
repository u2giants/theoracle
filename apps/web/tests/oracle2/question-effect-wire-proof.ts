/** Retained invented ACTUAL backend wire conformance, no current authority. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseConversationResponse,type ConversationSnapshot} from '@oracle/shared/protected-conversation-contract';
const paths=process.argv.slice(2);assert.equal(paths.length,5,'four exact retained wires +owned report path required');
const reports=[];
for(let i=0;i<4;i++){
 const path=paths[i]!;const raw=readFileSync(path);const packet=parseConversationResponse(raw) as ConversationSnapshot;
 assert.equal(packet.mode,'interview');assert.equal(packet.question_count,1);assert.equal(packet.question_id,packet.pending_question_id);assert.equal(packet.company_policy_confirmed,false);
 const effect=packet.qualified_effect;assert.ok(effect);assert.equal(effect.semantic_entailment_verified,false);assert.equal(effect.business_accepted,false);assert.equal(effect.automatic_retry_allowed,false);
 if(i%2===0){assert.equal(effect.state,'observed');assert.equal(effect.provider_dispatched,true);assert.ok(effect.answer);assert.equal(effect.answer.model_version,effect.model_version);assert.equal(effect.answer.model_content_hash,effect.model_content_hash);assert.ok((effect.answer.records as unknown[]).length);if(i===0){assert.equal(effect.purpose,'qualified-query-embedding-v1');assert.equal(effect.answer.query_embedding_used,true);assert.equal(effect.answer.provider_generation_used,false);}else{assert.equal(effect.purpose,'qualified-answer-synthesis-v1');assert.equal(effect.answer.provider_generation_used,true);assert.equal(effect.answer.query_embedding_used,false);assert.equal(effect.synthesis?.interpretation,null);
 const refs=effect.synthesis!;assert.equal(refs.protocol,'qualified-answer-synthesis-references-v1');
 const groups=refs.factual_groups as {classification:string;assertion_ids:string[]}[];assert.ok(groups.length);
 const recordIds=new Set((effect.answer.records as {assertion:{assertion_id:string}}[]).map(r=>r.assertion.assertion_id));
 assert.deepEqual(new Set(groups.flatMap(g=>g.assertion_ids)),recordIds);
 for(const kind of ['nested','foreign','missing','duplicate','opposition','coverage','gaps']){
  const forged=structuredClone(packet) as unknown as {qualified_effect:{synthesis:{factual_groups:Record<string,unknown>[];coverage:Record<string,unknown>;gap_codes:string[]}}};const syn=forged.qualified_effect.synthesis;const group=syn.factual_groups[0]!;const ids=group.assertion_ids as string[];
  if(kind==='nested')group.records=effect.answer.records;
  else if(kind==='foreign')ids[0]='11111111-1111-4111-8111-111111111111';
  else if(kind==='missing')syn.factual_groups.shift();
  else if(kind==='duplicate')ids.push(ids[0]!);
  else if(kind==='opposition')group.classification=group.classification==='opposed'?'reported':'opposed';
  else if(kind==='coverage')syn.coverage.entire_company_verified=true;
  else syn.gap_codes=[];
  assert.throws(()=>parseConversationResponse(Buffer.from(JSON.stringify(forged))),kind+' must refuse on actual nonempty wire');
 }
 }}
 else{assert.equal(effect.state,'unknown');assert.equal(effect.provider_dispatched,null);assert.equal(effect.answer,null);assert.equal(effect.native_receipt_sha256,null);assert.equal(effect.model_id,null);}
 reports.push({wire_sha256:createHash('sha256').update(raw).digest('hex'),state:effect.state,purpose:effect.purpose,question_count:packet.question_count,original_bound:true,source:'retained-invented-actual-SQL024-native-Budget-SDK-wire',current_authority:false});
}
writeFileSync(paths[4]!,JSON.stringify({schema_version:1,retained_wire_conformance:true,current_runtime_or_browser_authority:false,semantic_qualification:false,business_accepted:false,results:reports},null,2)+'\n',{mode:0o600});
process.stdout.write('Four actual retained backend wires parsed unchanged; no current/browser/authority claim.\n');
