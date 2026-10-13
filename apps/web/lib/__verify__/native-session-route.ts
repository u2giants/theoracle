import assert from 'node:assert/strict';
import { POST } from '../../app/api/consultant/native-acceptance/session/route';
const url='https://native.example.test/api/consultant/native-acceptance/session';
const headers={'origin':'https://native.example.test','content-type':'application/json'};
async function main(){
  // HTTP/2 and Next can omit content-length: a bounded body must still reach auth.
  assert.equal((await POST(new Request(url,{method:'POST',headers,body:JSON.stringify({token:'invalid-public-test-token'})}))).status,401);
  assert.equal((await POST(new Request(url,{method:'POST',headers,body:'x'.repeat(8193)}))).status,400);
  assert.equal((await POST(new Request(url,{method:'POST',headers:{...headers,origin:'https://foreign.example.test'},body:'{}'}))).status,400);
  assert.equal((await POST(new Request(url,{method:'POST',headers:{...headers,'transfer-encoding':'chunked'},body:'{}'}))).status,400);
  assert.equal((await POST(new Request(url,{method:'POST',headers,body:JSON.stringify({token:'invalid',actor:'unadmitted'})}))).status,400);
  console.log('native session route: 5 checks passed');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
