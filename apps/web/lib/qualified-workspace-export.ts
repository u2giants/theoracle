/** Text-only exports from a freshly authorized workspace response. */
import type {WorkspaceAnswerPacketV1} from '@oracle/shared/protected-natural-question-contract';
const record=(v:unknown):Record<string,unknown>|null=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:null;
const rows=(v:unknown):unknown[]=>Array.isArray(v)?v:[];
const text=(v:unknown)=>typeof v==='string'?v:'';
export function spreadsheetCellV1(v:string):string{
 const safe=/^[\s]*[=+\-@]/u.test(v)||/^[\t\r\n]/u.test(v)?"'"+v:v;
 return '"'+safe.replaceAll('"','""')+'"';
}
export function workspaceCsvV1(packet:WorkspaceAnswerPacketV1,origin:string,now:number):string{
 const url=new URL(origin),end=Date.parse(packet.expires_at),checked=Date.parse(packet.checked_at);if(url.protocol!=='https:'||url.origin!==origin||!Number.isFinite(now)||!Number.isFinite(end)||!Number.isFinite(checked)||checked>now||checked>=end||now>=end)throw new Error('Current export unavailable');
 const answer=record(packet.result.answer);if(!answer)throw new Error('Current export unavailable');
 const lines:string[][]=[['Record','Text','Provenance','Scope','Valid from','Valid to','Evidence kind','Exact quote','Original link','Model version','Checked at','Coverage']];
 const coverage=JSON.stringify(answer.coverage);
 for(const raw of rows(answer.records)){
  const item=record(raw),assertion=record(item?.assertion),evidence=record(item?.evidence);if(!assertion||!evidence)throw new Error('Current export unavailable');
  for(const kind of ['supporting','opposing','unknown','temporal'])for(const rawQuote of rows(evidence[kind])){
   const quote=record(rawQuote),ref=record(quote?.ref);if(!quote||!ref)throw new Error('Current export unavailable');
   lines.push([text(assertion.predicate),text(assertion.value),text(assertion.provenance),JSON.stringify(assertion.scope),text(assertion.valid_from),text(assertion.valid_to),kind,text(quote.quote),origin+'/consultant/replacement/originals/'+encodeURIComponent(String(ref.source_id))+'/'+String(ref.revision),String(packet.result.model_version),packet.checked_at,coverage]);
  }
 }
 // These fixed rows preserve bounds and caveats even for an empty current model.
 lines.push(['Coverage',coverage,'Reported documentary records; company policy unconfirmed','','','','','','',String(packet.result.model_version),packet.checked_at,'Company-wide completeness unverified']);
 for(const caveat of rows(answer.caveats))lines.push(['Caveat',String(caveat),'','','','','','','','','','']);
 return '\uFEFF'+lines.map(line=>line.map(spreadsheetCellV1).join(',')).join('\r\n')+'\r\n';
}
const escape=(v:unknown)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export function workspaceSopHtmlV1(packet:WorkspaceAnswerPacketV1,origin:string,now:number):string{
 // Reuse the CSV validator for the exact origin, current window and core shape.
 workspaceCsvV1(packet,origin,now);
 const original=(raw:unknown)=>{const q=record(raw),r=record(q?.ref);if(!q||!r)throw new Error('Current export unavailable');return '<blockquote><p>'+escape(q.quote)+'</p><a href="'+escape(origin+'/consultant/replacement/originals/'+encodeURIComponent(String(r.source_id))+'/'+String(r.revision))+'">Open original under current access</a></blockquote>';};
 const workflows=rows(packet.result.workflows).map(raw=>{
  const w=record(raw);if(!w)throw new Error('Current export unavailable');
  const items=rows(w.items).map(raw=>{const item=record(raw);if(!item||!record(item.value))throw new Error('Current export unavailable');return item;});
  const labels=new Map(items.map(item=>[text(item.identity),text(record(item.value)?.label)||text(record(item.value)?.wording)||'Unspecified decision']));
  const name=(v:unknown)=>labels.get(text(v))||'Role or activity not named in this record';
  const description=(item:Record<string,unknown>)=>{const v=record(item.value)!;switch(item.collection){
   case 'steps':return ['Activity',text(v.label)+(v.role_id?' — role: '+name(v.role_id):' — role not recorded')];
   case 'gateways':return ['Decision or parallel branch',text(v.kind).replaceAll('_',' ')];
   case 'transitions':return [v.rework===true?'Rework':'Sequence',name(v.from_id)+' → '+name(v.to_id)+(v.condition_id?' — condition: '+name(v.condition_id):'')];
   case 'conditions':return ['Condition',text(v.wording)+(v.applicability==='unknown'?' — applicability unknown':'')];
   case 'roles':return ['Responsibility',name(v.step_id)+' — '+name(v.role_id)];
   case 'artifacts':return ['Document or output',text(v.label)];
   case 'handoffs':return ['Handoff',name(v.from_step)+' → '+name(v.to_step)+' — '+name(v.artifact_id)];
   default:throw new Error('Current export unavailable');
  }};
  return '<section><h2>Reported process</h2><p>Scope: '+escape(w.scope)+'; completeness: '+escape(w.completeness)+'</p>'+items.map(item=>{const [heading,wording]=description(item);return '<article><h3>'+escape(heading)+'</h3><p>'+escape(wording)+'</p>'+rows(item.evidence).map(original).join('')+'</article>';}).join('')+'</section>';
 }).join('');
 const answer=record(packet.result.answer)!;
 const accounts=rows(answer.records).map(raw=>{const item=record(raw),a=record(item?.assertion),e=record(item?.evidence);if(!a||!e)throw new Error('Current export unavailable');return '<article><h2>'+escape(a.predicate)+'</h2><p>'+escape(a.value)+'</p><p>Scope: '+escape(JSON.stringify(a.scope))+'</p><p>Validity: '+escape(a.valid_time)+'; '+escape(a.valid_from)+' to '+escape(a.valid_to)+'</p>'+['supporting','opposing','unknown','temporal'].map(kind=>'<section><h3>'+kind+'</h3>'+rows(e[kind]).map(original).join('')+'</section>').join('')+'</article>';}).join('');
 return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Reported process and original evidence</title><body><h1>Reported process and original evidence</h1><p>Reported documentary records; company-policy approval and company-wide completeness are not established. Opening originals requires separate current access.</p><p>Declared population: '+escape(packet.result.declared_population)+'</p><p>Model version '+escape(packet.result.model_version)+'; checked '+escape(packet.checked_at)+'</p><p>Coverage: '+escape(JSON.stringify(answer.coverage))+'</p>'+workflows+accounts+'<section><h2>Caveats</h2>'+rows(answer.caveats).map(c=>'<p>'+escape(c)+'</p>').join('')+'</section></body></html>';
}
