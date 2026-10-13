// Public artifact compiler only. Hash association is NOT independent admission.
import {readFileSync,writeFileSync,openSync,fstatSync,closeSync,constants} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const exact=(value,fields)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join('|')===fields.sort().join('|');
const routes=[['/consultant/native-acceptance',['GET','HEAD']],['/api/consultant/native-acceptance',['GET','POST']],['/api/consultant/native-acceptance/session',['POST','DELETE']],['/api/consultant/native-acceptance/source',['GET']]];
const token='__ORACLE_NATIVE_BROWSER_COMPILED_RULE_REQUIRED__';
export function compileIngress({staticBytes,sourceBytes,association,publicHost,expectedRevision,expectedImageDigest,composeTemplate}){
  if(!/^[a-f0-9]{40}$/.test(expectedRevision)||!/^sha256:[a-f0-9]{64}$/.test(expectedImageDigest)
    ||!/^[a-z0-9][a-z0-9.-]{1,250}[a-z0-9]$/.test(publicHost)||publicHost.includes('..')||publicHost==='oracle.designflow.app')throw Error('Ingress inputs denied');
  if(staticBytes.length>1048576||sourceBytes.length>1048576)throw Error('Ingress inputs denied');
  const manifest=JSON.parse(staticBytes),source=JSON.parse(sourceBytes);
  if(!exact(manifest,['schema_version','source_revision','assets'])||manifest.schema_version!==1||manifest.source_revision!==expectedRevision
    ||!Array.isArray(manifest.assets)||manifest.assets.length!==11)throw Error('Ingress inputs denied');
  if(!exact(association,['schema_version','source_revision','image_digest','static_manifest_sha256','source_offer_manifest_sha256','source_archive_sha256','public_artifact_only'])
    ||association.schema_version!==1||association.public_artifact_only!==true||association.source_revision!==expectedRevision
    ||association.image_digest!==expectedImageDigest||association.static_manifest_sha256!==hash(staticBytes)
    ||association.source_offer_manifest_sha256!==hash(sourceBytes))throw Error('Ingress inputs denied');
  if(source.schema_version!==1||source.revision!==expectedRevision||source.private_data_included!==false
    ||!/^[a-f0-9]{64}$/.test(source.archive_sha256)||source.archive_sha256!==association.source_archive_sha256
    ||!source.files||typeof source.files!=='object'||Array.isArray(source.files)
    ||source.source_hash!==hash(JSON.stringify(source.files)))throw Error('Ingress inputs denied');
  for(const path of ['dev/oracle2/browser/Dockerfile','dev/oracle2/browser/Dockerfile.dockerignore','dev/oracle2/browser/compile-ingress.mjs','dev/oracle2/browser/coolify-companion.yaml','apps/web/proxy.ts','apps/web/lib/native-browser-runtime.mjs'])
    if(!/^[a-f0-9]{64}$/.test(source.files[path]??''))throw Error('Ingress inputs denied');
  if(source.files['dev/oracle2/browser/compile-ingress.mjs']!==hash(readFileSync(new URL('./compile-ingress.mjs',import.meta.url)))
    ||source.files['dev/oracle2/browser/coolify-companion.yaml']!==hash(composeTemplate))throw Error('Ingress inputs denied');
  const paths=new Set();
  for(const asset of manifest.assets){
    if(!exact(asset,['path','sha256'])||typeof asset.path!=='string'||!/^\/_next\/static\/[a-zA-Z0-9_./~-]+$/.test(asset.path)
      ||asset.path.includes('..')||asset.path.includes('//')||asset.path.length>300||!/^[a-f0-9]{64}$/.test(asset.sha256)||paths.has(asset.path))throw Error('Ingress inputs denied');
    paths.add(asset.path);
  }
  const methods=values=>'('+values.map(value=>`Method(\`${value}\`)`).join(' || ')+')';
  const fixed=routes.map(([path,verbs])=>`(Path(\`${path}\`) && ${methods(verbs)})`);
  fixed.push('(('+[...paths].sort().map(path=>`Path(\`${path}\`)`).join(' || ')+') && '+methods(['GET','HEAD'])+')');
  const rule=`Host(\`${publicHost}\`) && (${fixed.join(' || ')})`;
  if(typeof composeTemplate!=='string'||composeTemplate.split(token).length!==2
    ||composeTemplate.includes('ORACLE_NATIVE_BROWSER_ROUTE_RULE')||composeTemplate.includes('PathPrefix('))throw Error('Ingress inputs denied');
  // Only this compiler token is substituted. No arbitrary rule input exists.
  const compose=composeTemplate.replace(token,rule)
    .replace('${ORACLE_NATIVE_BROWSER_IMAGE:?immutable GHCR digest required}',`ghcr.io/u2giants/theoracle-native-browser@${expectedImageDigest}`)
    .replace('${ORACLE_NATIVE_BROWSER_HOST:?dedicated reviewed HTTPS hostname required}',publicHost)
    .replace('${ORACLE_NATIVE_BROWSER_REVISION:?exact source SHA required}',expectedRevision);
  return {schema_version:1,purpose:'public-invented-native-browser-candidate',source_revision:expectedRevision,image_digest:expectedImageDigest,
    public_host:publicHost,static_manifest_sha256:hash(staticBytes),source_offer_manifest_sha256:hash(sourceBytes),source_archive_sha256:source.archive_sha256,
    exact_static_assets:[...paths].sort(),platform_route_value:rule,platform_route_sha256:hash(rule),compose_sha256:hash(compose),compose,
    authenticated_artifact_association:false,independent_review_required:true,authorizes_runtime:false,admission:false,live_acceptance:false};
}
function bounded(path){const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);try{const info=fstatSync(fd);if(!info.isFile()||info.size>1048576)throw Error('Ingress inputs denied');return readFileSync(fd);}finally{closeSync(fd);}}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{
    const {values,tokens}=parseArgs({tokens:true,options:Object.fromEntries(['static-manifest','source-manifest','association','public-host','revision','image-digest','output','compose-output'].map(name=>[name,{type:'string'}])),allowPositionals:false,strict:true});
    if(Object.values(values).length!==8||new Set(tokens.filter(t=>t.kind==='option').map(t=>t.name)).size!==tokens.filter(t=>t.kind==='option').length)throw Error('Ingress inputs denied');
    const result=compileIngress({staticBytes:bounded(values['static-manifest']),sourceBytes:bounded(values['source-manifest']),association:JSON.parse(bounded(values.association)),publicHost:values['public-host'],expectedRevision:values.revision,expectedImageDigest:values['image-digest'],composeTemplate:readFileSync(new URL('./coolify-companion.yaml',import.meta.url),'utf8')});
    writeFileSync(values['compose-output'],result.compose,{flag:'wx',mode:0o600});
    const {compose,...receipt}=result;writeFileSync(values.output,JSON.stringify(receipt)+'\n',{flag:'wx',mode:0o600});
    console.log(JSON.stringify({source_revision:result.source_revision,exact_static_assets:11,authorizes_runtime:false}));
  }catch{console.error('Public ingress compilation denied.');process.exit(1);}
}
