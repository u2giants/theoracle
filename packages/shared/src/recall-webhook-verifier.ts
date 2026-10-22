/** Strict replacement envelope only; never capture admission. */
import crypto from 'node:crypto';
export function verifyReplacementRecallRequestV1(args: {
  secret: string; headers: Headers; payload: string | null;
}): void {
  const deny = (): never => { throw new Error('Recall verification refused'); };
  const { secret, headers, payload } = args;
  if (['svix-id', 'svix-timestamp', 'svix-signature'].some((key) => headers.has(key))) deny();
  const id = headers.get('webhook-id');
  const timestamp = headers.get('webhook-timestamp');
  const signature = headers.get('webhook-signature');
  if (!id || !/^[\x21-\x7e]{1,256}$/.test(id) || id.includes(',')) deny();
  if (!timestamp || !/^(0|[1-9][0-9]{0,12})$/.test(timestamp)) deny();
  const seconds = Number(timestamp);
  const now = Date.now() / 1000;
  if (!Number.isSafeInteger(seconds) || seconds < now - 300 || seconds > now + 30) deny();
  if (typeof payload !== 'string' || Buffer.byteLength(payload, 'utf8') > 1024 * 1024
      || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(payload)) deny();
  if (typeof secret !== 'string' || !secret.startsWith('whsec_') || secret.length > 178) deny();
  const keyText = secret.slice(6);
  const key = Buffer.from(keyText, 'base64');
  if (key.length < 32 || key.length > 128 || key.toString('base64') !== keyText) deny();
  if (!signature || signature.length > 196) return deny();
  const signatures = signature.split(' ');
  if (signatures.length < 1 || signatures.length > 4) deny();
  const expected = crypto.createHmac('sha256', key).update(`${id}.${timestamp}.${payload}`).digest();
  let matched = false;
  for (const item of signatures) {
    if (!/^v1,[A-Za-z0-9+/]{43}=$/.test(item)) deny();
    const actual = Buffer.from(item.slice(3), 'base64');
    if (actual.length !== 32 || actual.toString('base64') !== item.slice(3)) deny();
    matched = crypto.timingSafeEqual(expected, actual) || matched;
  }
  if (!matched) deny();
}
