/** Descriptive upload observations. Never source qualification or remote stop. */
export const UPLOAD_CHUNK_BYTES=2*1024*1024;
export const UPLOAD_MAX_BYTES=25*1024*1024;
export const UPLOAD_MAX_REQUEST_BYTES=2850000;
export interface UploadedSourceSnapshot {
 readonly sourceId:string;readonly revision:number;readonly originalSha256:string;
 readonly byteCount:number;readonly mediaType:'application/pdf';readonly filename:string;
 readonly state:'awaiting_original_reading';readonly qualifiedSourceRef:null;
}
export interface UploadResponse {
 readonly schema_version:1;
 readonly state:'reserved'|'receiving'|'finalizing'|'committed'|'cancelled'|'expired'|'UNKNOWN';
 readonly reservation_id:string;readonly source_id:string;readonly revision:number;
 readonly begin_sha256:string;readonly received_bytes:number;readonly next_chunk_index:number;
 readonly valid_until:string;readonly qualification:false;readonly remote_stop_proven:false;
 readonly observation_only:true;readonly source_snapshot:UploadedSourceSnapshot|null;
}
