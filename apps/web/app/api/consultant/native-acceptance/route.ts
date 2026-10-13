import { authorizeNativeRequest } from '@/lib/native-browser-auth';
import { pilotWorkspaceId } from '@/lib/oracle2-store';
import { nativeHandlers, loadSettings, currentNativeJob, nativeTransport } from '@/lib/native-acceptance';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const handle=nativeHandlers({authorize:authorizeNativeRequest,workspace:pilotWorkspaceId,settings:loadSettings,
  current:currentNativeJob,transport:nativeTransport,clock:()=>Math.floor(Date.now()/1000)});
export async function POST(req:Request){return handle(req,'admit');}
export async function GET(req:Request){return handle(req,'result');}
