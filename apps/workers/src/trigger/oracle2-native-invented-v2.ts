import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';

export const NATIVE_V2_GRAPH='oracle_operating_model_v1_cc904285f2134a579cdb06f8c278d3ec_62ec10d787254fb89668035dd89c9acd_1_5c56ede7638c4f51bd98d9e6cad3a8d0';
export function validateNativeV2Payload(payload:unknown,env:NodeJS.ProcessEnv=process.env):asserts payload is {jobId:string;workspaceId:string}{
 const forbidden=['ORACLE_NATIVE_GRAPH_PROJECTOR_PASSWORD','ORACLE_NATIVE_PROJECTOR_DATABASE_URL','ORACLE2_PROJECTOR_DATABASE_URL','TRIGGER_PAT','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY','ZHIPU_API_KEY','AZURE_OPENAI_API_KEY','ORACLE2_NATIVE_TRIGGER_BUNDLE','ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256','ORACLE2_PREVIEW_ADMIN_URL','ORACLE_NATIVE_ADMIN_URL','DATABASE_URL','ORACLE2_DATABASE_URL','TRIGGER_ACCESS_TOKEN','ORACLE2_PROJECTOR_GRAPH_URL','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL'];
 if(forbidden.some(k=>env[k]!==undefined))throw new Error('V2 executor rejects old or privileged credentials');
 if(!payload||typeof payload!=='object'||Array.isArray(payload)||Object.keys(payload).sort().join('|')!=='jobId|workspaceId'||(payload as {jobId:unknown}).jobId!=='6714d4ed-51df-4c38-9155-c456edf7b727'||(payload as {workspaceId:unknown}).workspaceId!=='cc904285-f213-4a57-9cdb-06f8c278d3ec')throw new Error('New opaque invented test identity required');
}

export function validateNativeV2Result(value:unknown,payload:{jobId:string;workspaceId:string},now=Math.floor(Date.now()/1000)):asserts value is Record<string,unknown>{
 if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('New native test did not complete');
 const v=value as Record<string,unknown>;
    if (Object.keys(v).sort().join('|')!==['schema_version','state','job_id','workspace_id','runtime_hash','release_hash','artifact_hash','result_sha256','sdk_version','graph_name','expires_at'].sort().join('|')||v.schema_version!==1||!['runtime_hash','release_hash','artifact_hash','result_sha256'].every(k=>typeof v[k]==='string'&&/^[a-f0-9]{64}$/.test(v[k] as string))||!Number.isSafeInteger(v.expires_at)||(v.expires_at as number)<=now||v.graph_name!==NATIVE_V2_GRAPH||v.state !== 'completed' || v.job_id !== payload.jobId
      || v.workspace_id !== payload.workspaceId || v.sdk_version !== '1.4.0') {
      throw new Error('New native test did not complete');
    }
}

// Isolated fresh invented permission only. No source text, retry or old job.
export const oracle2NativeInventedV2 = task({
  id: 'oracle2-native-invented-v2',
  maxDuration: 120,
  retry: { maxAttempts: 1 },
  run: async (payload: { jobId: string; workspaceId: string }, { ctx }) => {
    validateNativeV2Payload(payload);
    const result = await python.runScript('./oracle2-python/oracle_brain/hosting/native_trigger_v2.py',
      [JSON.stringify(payload), ctx.run.id]);
    let value: Record<string, unknown>;
    try { value = JSON.parse(result.stdout); } catch { throw new Error('Native test metadata unavailable'); }
    validateNativeV2Result(value,payload);
    return value;
  },
});
