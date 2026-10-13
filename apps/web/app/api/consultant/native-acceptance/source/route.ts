import { deliverPublicSource } from '@/lib/public-source-offer';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export const GET=(req:Request)=>deliverPublicSource(req);
