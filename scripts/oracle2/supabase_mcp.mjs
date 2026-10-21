// Started AFTER the existing ai-devops MCP credential/session guard.
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { readPrivateTarget } from '../../dev/oracle2/private-target-profile.mjs';

export function supabaseMcpCommand(project, platform = process.platform) {
  // Routing pin is checked by readPrivateTarget; this check also excludes shell syntax.
  if (typeof project !== 'string' || !/^[a-z]{20}$/.test(project))
    throw new Error('Private target metadata unavailable');
  const args = ['-y','@supabase/mcp-server-supabase@latest','--read-only','--project-ref',project];
  return platform === 'win32'
    ? { command: 'cmd.exe', args: ['/d','/s','/c','npx',...args] }
    : { command: 'npx', args };
}
export function relayMcp(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: 'inherit' });
    const forward = signal => () => { if (child.exitCode === null && child.signalCode === null) child.kill(signal); };
    const listeners = ['SIGINT','SIGTERM'].map(signal => [signal, forward(signal)]);
    for (const [signal, listener] of listeners) process.on(signal, listener);
    const clean = () => { for (const [signal, listener] of listeners) process.removeListener(signal, listener); };
    child.once('error', () => { clean(); reject(new Error('Oracle MCP startup unavailable')); });
    child.once('close', (code, signal) => { clean(); resolve({ code, signal }); });
  });
}
export async function runSupabaseMcp() {
  const { command, args } = supabaseMcpCommand(readPrivateTarget('oracle_supabase_project'));
  const result = await relayMcp(command, args);
  if (result.signal) { process.kill(process.pid, result.signal); return; }
  process.exitCode = result.code ?? 1;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  await runSupabaseMcp();
