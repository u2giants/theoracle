import { requestModelReview } from '../../../../../../../lib/replacement-protected-client';
export const runtime='nodejs';
export const dynamic='force-dynamic';
/** Actual fixed authenticated review owner. Never fixture fallback or dispatch. */
export async function POST(request:Request):Promise<Response>{return requestModelReview(request);}
