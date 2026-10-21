// Owner: Oracle coordinator (#27). Metadata-only CI custody, never a credential loader.
import { createHash } from 'node:crypto';
import { mkdirSync, openSync, writeFileSync, closeSync, lstatSync, unlinkSync, rmdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { validateTargetDocument } from './private-target-profile.mjs';

const fail = () => { throw new Error('Required pinned CI target metadata unavailable'); };
const expectedSha = 'c28efde80ed05f5eb506d7bd651c70c5d802b1f82d67a915a52910e337c3bf3e';
function targetPath(env) {
  if (!env.RUNNER_TEMP?.startsWith('/') || !/^\d+$/.test(env.GITHUB_RUN_ID ?? '')
      || !/^\d+$/.test(env.GITHUB_RUN_ATTEMPT ?? '')) fail();
  const path = join(env.RUNNER_TEMP, `oracle-target-${env.GITHUB_RUN_ID}-${env.GITHUB_RUN_ATTEMPT}`, 'targets.json');
  if (env.ORACLE_TARGET_PROFILE_PATH !== path) fail();
  return path;
}
try {
  const path = targetPath(process.env);
  if (process.argv.includes('--cleanup')) {
    let parent;
    try { parent = lstatSync(dirname(path)); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    if (parent) {
      if (!parent.isDirectory() || parent.isSymbolicLink() || parent.uid !== process.getuid() || (parent.mode & 0o077)) fail();
      let leaf;
      try { leaf = lstatSync(path); } catch (e) { if (e.code !== 'ENOENT') throw e; }
      if (leaf) {
        if (!leaf.isFile() || leaf.isSymbolicLink() || leaf.nlink !== 1 || leaf.uid !== process.getuid() || (leaf.mode & 0o077)) fail();
        unlinkSync(path);
      }
      rmdirSync(dirname(path));
    }
  } else {
    const raw = process.env.ORACLE_TARGET_PROFILE_JSON;
    if (typeof raw !== 'string' || Buffer.byteLength(raw) > 16384
        || createHash('sha256').update(raw).digest('hex') !== expectedSha) fail();
    const values = validateTargetDocument(JSON.parse(raw));
    // GitHub's whole-JSON masking does not automatically mask each member.
    for (const value of Object.values(values)) process.stdout.write(`::add-mask::${value}\n`);
    mkdirSync(dirname(path), { mode: 0o700 });
    const parent = lstatSync(dirname(path));
    if (!parent.isDirectory() || parent.isSymbolicLink() || parent.uid !== process.getuid() || (parent.mode & 0o077)) fail();
    const fd = openSync(path, 'wx', 0o600);
    try { writeFileSync(fd, raw); } finally { closeSync(fd); }
  }
} catch { process.stderr.write('Required pinned CI target metadata unavailable\n'); process.exitCode = 1; }
