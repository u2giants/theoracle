#!/usr/bin/env node
// Launch the Supabase MCP server for this repo's .mcp.json `supabase-oracle`
// entry (issue #431). The entry routes through the ai-devops secret launcher
// (mcp-launch.cmd / mcp-launch.sh), which injects SUPABASE_ACCESS_TOKEN from
// 1Password into this process; the spawned server inherits it. No secret and no
// project ref lives in this repo.
//
// Replaces scripts/oracle2/supabase_mcp.mjs, deleted with Oracle 2 in #406.
// The old private-target registry (dev/oracle2 pin hashes) was retired with it;
// the Supabase project ref is private metadata and is read at launch from the
// machine profile: ~/.config/oracle/targets.json, key `oracle_supabase_project`
// (ORACLE_TARGET_PROFILE_PATH overrides the path). Keep --read-only: migrations
// go through `pnpm db:migrate` only (docs/development.md).
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join } from 'node:path'
import { pathToFileURL } from 'node:url'

const fail = (msg) => {
  throw new Error(msg)
}

export function assertProjectShape(project) {
  if (typeof project !== 'string' || !/^[a-z]{20}$/.test(project)) fail('Private target metadata unavailable')
  return project
}

export function readOracleSupabaseProject(env = process.env, home = homedir()) {
  const override = env.ORACLE_TARGET_PROFILE_PATH
  const path = override
    ? isAbsolute(override)
      ? override
      : fail('ORACLE_TARGET_PROFILE_PATH must be absolute')
    : join(home, '.config', 'oracle', 'targets.json')
  let doc
  try {
    doc = JSON.parse(readFileSync(path, 'utf8'))
  } catch {
    fail('Private target metadata unavailable')
  }
  return assertProjectShape(doc?.targets?.oracle_supabase_project)
}

export function supabaseMcpCommand(project, platform = process.platform) {
  assertProjectShape(project)
  const args = ['-y', '@supabase/mcp-server-supabase@latest', '--read-only', '--project-ref', project]
  return platform === 'win32'
    ? { command: 'cmd.exe', args: ['/d', '/s', '/c', 'npx', ...args] }
    : { command: 'npx', args }
}

export function relayMcp(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: 'inherit' })
    const forward = (signal) => () => {
      if (child.exitCode === null && child.signalCode === null) child.kill(signal)
    }
    const listeners = ['SIGINT', 'SIGTERM'].map((signal) => [signal, forward(signal)])
    for (const [signal, listener] of listeners) process.on(signal, listener)
    const clean = () => {
      for (const [signal, listener] of listeners) process.removeListener(signal, listener)
    }
    child.once('error', () => {
      clean()
      reject(new Error('Supabase MCP startup unavailable'))
    })
    child.once('close', (code, signal) => {
      clean()
      resolve({ code, signal })
    })
  })
}

export async function runSupabaseMcp() {
  const { command, args } = supabaseMcpCommand(readOracleSupabaseProject())
  const result = await relayMcp(command, args)
  if (result.signal) {
    process.kill(process.pid, result.signal)
    return
  }
  process.exitCode = result.code ?? 1
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await runSupabaseMcp()
