import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { assertProjectShape, readOracleSupabaseProject, supabaseMcpCommand, relayMcp } from '../scripts/mcp-supabase-launch.mjs'

const project = 'abcdefghij0123456789'

test('accepts lowercase letters and digits, rejects malformed refs without exposing them', () => {
  assert.equal(assertProjectShape(project), project)
  assert.equal(assertProjectShape('a'.repeat(20)), 'a'.repeat(20))
  for (const value of [undefined, null, 123, '', 'a'.repeat(19), 'a'.repeat(21), 'A'.repeat(20), '-'.repeat(20), 'a'.repeat(20) + '\n']) {
    assert.throws(() => assertProjectShape(value), { message: 'oracle_supabase_project must contain exactly 20 lowercase letters or digits' })
  }
})

test('reads default and absolute override profiles, rejects relative paths and unavailable metadata', (t) => {
  const home = mkdtempSync(join(tmpdir(), 'oracle-mcp-test-'))
  t.after(() => rmSync(home, { recursive: true, force: true }))
  const dir = join(home, '.config', 'oracle')
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'targets.json'), JSON.stringify({ targets: { oracle_supabase_project: project } }))
  assert.equal(readOracleSupabaseProject({}, home), project)
  const override = join(home, 'override.json')
  writeFileSync(override, JSON.stringify({ targets: { oracle_supabase_project: 'b'.repeat(20) } }))
  assert.equal(readOracleSupabaseProject({ ORACLE_TARGET_PROFILE_PATH: override }, home), 'b'.repeat(20))
  assert.throws(() => readOracleSupabaseProject({ ORACLE_TARGET_PROFILE_PATH: 'relative.json' }, home), /must be absolute/)
  for (const content of ['{', '{}', JSON.stringify({ targets: { oracle_supabase_project: 'invalid' } })]) {
    writeFileSync(override, content)
    assert.throws(() => readOracleSupabaseProject({ ORACLE_TARGET_PROFILE_PATH: override }, home))
  }
  rmSync(override)
  assert.throws(() => readOracleSupabaseProject({ ORACLE_TARGET_PROFILE_PATH: override }, home), /Private target metadata unavailable/)
})

test('pins the server and preserves read-only and project restriction on both platforms', () => {
  const args = ['-y', '@supabase/mcp-server-supabase@0.4.5', '--read-only', '--project-ref', project]
  assert.deepEqual(supabaseMcpCommand(project, 'linux'), { command: 'npx', args })
  assert.deepEqual(supabaseMcpCommand(project, 'win32'), { command: 'cmd.exe', args: ['/d', '/s', '/c', 'npx', ...args] })
  assert.throws(() => supabaseMcpCommand('invalid'))
})

test('preserves spawn failure details and removes signal listeners', async () => {
  const before = ['SIGINT', 'SIGTERM'].map(signal => process.listenerCount(signal))
  await assert.rejects(relayMcp(join(tmpdir(), 'oracle-mcp-nonexistent-command'), []), error => {
    assert.equal(error.cause.code, 'ENOENT')
    assert.match(error.message, /Supabase MCP startup unavailable:.*ENOENT/)
    return true
  })
  assert.deepEqual(['SIGINT', 'SIGTERM'].map(signal => process.listenerCount(signal)), before)
})

test('relays the server exit code', async () => {
  assert.deepEqual(await relayMcp(process.execPath, ['-e', 'process.exit(7)']), { code: 7, signal: null })
})
