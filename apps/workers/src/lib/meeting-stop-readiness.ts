/** STOP service read-only readiness; never a claim or effect permission.
 * The same service must still prepare, claim once and recheck currentness.
 */
import {canonicalUuid,canonicalHash} from '@oracle/shared/protected-server-binding';
import type {MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
export function unclaimedMeetingStopReadyV1(packet:Readonly<MeetingWorkerPacketV1>):boolean{
 return packet.effect_purpose==='capture-leave'&&(packet.state==='idle'||packet.state==='prepared')
  &&canonicalUuid(packet.operation_id)&&canonicalUuid(packet.bot_id)&&canonicalHash(packet.request_sha256)
  &&packet.claim_event_id===null&&packet.executable===false&&packet.body_base64===null;
}
