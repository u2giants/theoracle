/** Separate employee-authenticated, read-only MCP. Legacy machine MCP unchanged. */
import { createMcpHandler } from 'mcp-handler';
import { z } from 'zod';
import { authenticatedConnectedAnswerChannel,requestEmployeeMcpAnswer,requestEmployeeMcpQuestion } from '../../../../../lib/replacement-protected-client';
import { unavailableControl } from '../../../../../lib/replacement-control-window';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export const maxDuration=30;
export async function POST(request:Request):Promise<Response>{
 if(!await authenticatedConnectedAnswerChannel(request,'mcp'))return unavailableControl();
 const handler=createMcpHandler(server=>{
  server.registerTool('oracle_ask_question',{
   title:'Ask the Oracle a business question',
   description:'Read qualified records for a natural business question. Ambiguous scope receives one clarification; retained quotes, conflicts, dates and incomplete coverage remain visible. No provider generation or company-wide completeness claim.',
   inputSchema:{question:z.string().min(1).max(8192)},
   annotations:{readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:false},
  },async ({question})=>{
   const response=await requestEmployeeMcpQuestion(request,question);
   if(response.status!==200)return {isError:true,content:[{type:'text' as const,text:'Current authorized evidence is unavailable.'}]};
   return {content:[{type:'text' as const,text:JSON.stringify(await response.json())}]};
  });
  server.registerTool('oracle_connected_answer',{
   title:'Read qualified Oracle records',
   description:'Read exact qualified records and retained original citations within your current authorized model. Select explicit process/customer/product/region scope. Unknowns, contradictions and historical recording time remain visible. No provider generation, query embedding, writes or company-wide completeness claim.',
   inputSchema:{query:z.unknown()},
   annotations:{readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:false},
  },async ({query})=>{
   const response=await requestEmployeeMcpAnswer(request,query);
   if(response.status!==200)return {isError:true,content:[{type:'text' as const,text:'Current authorized evidence is unavailable.'}]};
   const packet:unknown=await response.json();
   // The same strict authenticated consumer validated the complete response.
   return {content:[{type:'text' as const,text:JSON.stringify(packet)}]};
  });
 },{serverInfo:{name:'oracle-employee-qualified-records',version:'1.0.0'}},{basePath:'/api/consultant/mcp',disableSse:true,maxDuration:30,verboseLogs:false});
 return handler(request);
}
export async function GET():Promise<Response>{return unavailableControl(405);}
export async function DELETE():Promise<Response>{return unavailableControl(405);}
