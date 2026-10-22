// Configuration selection only. This document never installs or authorizes deployment.
import {createHash} from 'node:crypto';
import {canonicalJson,instant} from '@oracle/shared/protected-server-binding';
import {isAbsolute} from 'node:path';
import {readBoundedTargetJson,isPinnedTarget} from '../../dev/oracle2/private-target-profile.mjs';
const failure=()=>{throw new Error('Independent meetings target unavailable');};
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export const MEETING_TASK_FILES=Object.freeze(['oracle2-meeting-capture-create.ts','oracle2-meeting-capture-leave.ts','oracle2-meeting-capture-retrieve-pre-stop.ts','oracle2-meeting-capture-retrieve-post-stop.ts','oracle2-meeting-participation.ts','oracle2-meeting-ingress-normalize.ts','oracle2-meeting-outbox-pump.ts']);
export function resolveMeetingsTriggerProject(env=process.env,now=Date.now()){
 const path=env.ORACLE2_MEETINGS_TARGET_PATH,expected=env.ORACLE2_MEETINGS_TARGET_SHA256,project=env.ORACLE2_MEETINGS_TRIGGER_PROJECT_REF;
 if(typeof path!=='string'||!isAbsolute(path)||typeof expected!=='string'||! /^[a-f0-9]{64}$/.test(expected)||typeof project!=='string'||! /^proj_[a-z]{20}$/.test(project)||!Number.isFinite(now))return failure();
 const v=readBoundedTargetJson(path,{privateProfile:true});const keys=['schema_version','purpose','project_ref','issuer','reviewer','valid_from','valid_until','original_horizon'];
 if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).length!==keys.length||!keys.every(k=>Object.hasOwn(v,k))||v.schema_version!==1||v.purpose!=='oracle2-meetings-trigger-target-v1'||v.project_ref!==project||!uuid.test(v.issuer)||!uuid.test(v.reviewer)||v.issuer===v.reviewer||createHash('sha256').update(canonicalJson(v)).digest('hex')!==expected)return failure();
 const times=['valid_from','valid_until','original_horizon'].map(k=>instant(v[k]));
 if(!(times[0]<=now&&now<times[1]&&times[1]<=times[2]))return failure();
 const oldRefs=Object.entries(env).filter(([k])=>k==='TRIGGER_PROJECT_REF'||/^ORACLE2_.*TRIGGER_PROJECT_REF$/.test(k)&&k!=='ORACLE2_MEETINGS_TRIGGER_PROJECT_REF').map(([,value])=>value);
 if(isPinnedTarget('legacy_trigger_project',project)||isPinnedTarget('native_trigger_project',project)||oldRefs.includes(project))return failure();
 return project;
}
