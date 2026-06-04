// Decryption for Microsoft Graph "rich" change notifications.
//
// The transcript subscriptions (communications/adhocCalls/getAllTranscripts)
// require includeResourceData:true, which means Graph encrypts the resource
// payload before POSTing it to our webhook. The scheme (per Microsoft Graph
// "change notifications with resource data") is:
//
//   1. Graph generates a random symmetric key, RSA-OAEP-encrypts it with the
//      PUBLIC certificate we registered on the subscription, and sends it as
//      `dataKey` (base64).
//   2. The actual payload is AES-256-CBC encrypted (IV = first 16 bytes of the
//      symmetric key) and sent as `data` (base64).
//   3. `dataSignature` is an HMAC-SHA256 of the encrypted `data`, keyed by the
//      symmetric key — so we can verify the payload wasn't tampered with.
//
// We hold the PRIVATE key (PEM, from env) and reverse the process.

import crypto from 'node:crypto';

export interface GraphEncryptedContent {
  /** Base64 AES-256-CBC encrypted resource payload. */
  data: string;
  /** Base64 RSA-OAEP encrypted symmetric key. */
  dataKey: string;
  /** Base64 HMAC-SHA256 of `data`, keyed by the symmetric key. */
  dataSignature: string;
  encryptionCertificateId?: string;
  encryptionCertificateThumbprint?: string;
}

/**
 * Decrypt a Graph rich-notification payload and return the parsed resource
 * object. Throws if the signature doesn't verify (payload not trusted) or the
 * private key can't decrypt the data key (wrong/rotated cert).
 */
export function decryptResourceData(
  enc: GraphEncryptedContent,
  privateKeyPem: string,
): unknown {
  // 1. Recover the symmetric key. Graph uses RSA-OAEP with SHA-1 (Node's
  //    default OAEP hash), so RSA_PKCS1_OAEP_PADDING is correct here.
  const symmetricKey = crypto.privateDecrypt(
    {
      key: privateKeyPem,
      padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
    },
    Buffer.from(enc.dataKey, 'base64'),
  );

  // 2. Verify the HMAC before trusting / decrypting anything.
  const expectedSignature = crypto
    .createHmac('sha256', symmetricKey)
    .update(Buffer.from(enc.data, 'base64'))
    .digest('base64');
  if (
    !crypto.timingSafeEqual(
      Buffer.from(expectedSignature),
      Buffer.from(enc.dataSignature),
    )
  ) {
    throw new Error(
      'Graph notification signature mismatch — payload not trusted',
    );
  }

  // 3. AES-256-CBC decrypt. IV is the first 16 bytes of the symmetric key.
  const iv = symmetricKey.subarray(0, 16);
  const decipher = crypto.createDecipheriv('aes-256-cbc', symmetricKey, iv);
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(enc.data, 'base64')),
    decipher.final(),
  ]);

  return JSON.parse(decrypted.toString('utf8'));
}
