import { requestReplacementOriginal } from '../../../../../../../lib/replacement-protected-client';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export async function POST(request:Request):Promise<Response>{return requestReplacementOriginal(request);}
