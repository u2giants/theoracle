import { requestEmployeeConversation } from './replacement-protected-client';
import { privateControlHeaders } from './replacement-control-window';
export async function employeeConversationPOST(request:Request):Promise<Response>{
 try{const value=await requestEmployeeConversation(request);if(value)return Response.json(value,{status:value.state==='DENIED'?403:value.state==='CONFLICT'?409:200,headers:privateControlHeaders});}catch{/* Never expose private transport, identity or SQL details. */}
 return Response.json({error:'Conversation unavailable or outcome uncertain. Check saved status before submitting again.'},{status:503,headers:privateControlHeaders});
}
