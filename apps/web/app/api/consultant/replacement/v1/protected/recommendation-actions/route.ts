import {requestRecommendationActionsV1} from '@/lib/replacement-protected-client';
import {unavailableControl} from '@/lib/replacement-control-window';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export const POST=requestRecommendationActionsV1;
export const GET=()=>unavailableControl(405);
