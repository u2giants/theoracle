/** Private SAME protected-file owner shared by fixed installed consumers. */
import {constants,closeSync,fstatSync,lstatSync,openSync,readFileSync} from 'node:fs';
import {dirname,isAbsolute,parse,resolve} from 'node:path';
import {createHash} from 'node:crypto';
const unavailable=():never=>{throw new Error('Replacement control unavailable');};
const hash=/^[0-9a-f]{64}$/;
export const sha256=(value:Uint8Array|string):string=>createHash('sha256').update(value).digest('hex');
export interface PinnedFile { readonly path: string; readonly digest: string; readonly identity: string; readonly bytes: Buffer; }
export function protectedRead(path: string, expected: string): PinnedFile {
  if (!isAbsolute(path) || resolve(path) !== path || !hash.test(expected)) return unavailable();
  const parents = (): string => {
    let ancestor = dirname(path); const identities: string[] = [];
    for (;;) {
      const stat = lstatSync(ancestor);
      if (!stat.isDirectory() || stat.isSymbolicLink()) return unavailable();
      identities.push([ancestor,stat.dev,stat.ino,stat.mode,stat.uid].join(':'));
      if (ancestor === parse(ancestor).root) break; ancestor = dirname(ancestor);
    }
    return identities.join('|');
  };
  const parentIdentity = parents();
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const a = fstatSync(fd);
    if (!a.isFile() || a.nlink !== 1 || (a.mode & 0o077) !== 0 || a.uid !== process.getuid?.() || a.size < 1 || a.size > 65536) return unavailable();
    const bytes = readFileSync(fd); const b = fstatSync(fd), current = lstatSync(path);
    const identity = (s: typeof a) => [s.dev,s.ino,s.mode,s.uid,s.nlink,s.size,s.ctimeMs,s.mtimeMs].join(':');
    if (parentIdentity !== parents() || identity(a) !== identity(b) || identity(a) !== identity(current) || sha256(bytes) !== expected) return unavailable();
    return { path, digest: expected, identity: parentIdentity + '|' + identity(a), bytes };
  } finally { closeSync(fd); }
}
