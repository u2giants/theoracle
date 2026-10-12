import type { NextRequest } from 'next/server';
import { view } from '../../model/route';
export const dynamic='force-dynamic';
export async function GET(req:NextRequest,{params}:{params:Promise<{id:string}>}){const {id}=await params;return view(req,id);}
