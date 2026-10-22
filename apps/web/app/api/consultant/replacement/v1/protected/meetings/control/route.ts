import {requestReplacementMeetingControl} from '@/lib/replacement-protected-client';
import {unavailableControl} from '@/lib/replacement-control-window';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export const POST=requestReplacementMeetingControl;
export function GET(){return unavailableControl(405);}
export const PUT=GET;
export const PATCH=GET;
export const DELETE=GET;
export const OPTIONS=GET;
export const HEAD=GET;
