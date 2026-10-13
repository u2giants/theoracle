import { readFileSync } from 'node:fs';
import { checkServerIdentity, type PeerCertificate } from 'node:tls';
import postgres from 'postgres';

// postgres.js does not load libpq's sslrootcert file parameter. Translate it
// explicitly while retaining certificate and hostname verification.
export function pilotPostgres(url: string) {
  const parsed = new URL(url);
  const root = parsed.searchParams.get('sslrootcert');
  if (!root || root === 'system') {
    return postgres(url, { max: 1, connect_timeout: 5 });
  }
  if (parsed.searchParams.get('sslmode') !== 'verify-full') {
    throw new Error('Custom PostgreSQL trust requires sslmode=verify-full');
  }
  const ca = readFileSync(root, 'utf8');
  const hostname = parsed.hostname.replace(/^\[|\]$/g, '');
  parsed.searchParams.delete('sslrootcert');
  parsed.searchParams.delete('sslmode');
  return postgres(parsed.toString(), {
    max: 1,
    connect_timeout: 5,
    ssl: {
      ca,
      rejectUnauthorized: true,
      checkServerIdentity: (_servername: string, certificate: PeerCertificate) => checkServerIdentity(hostname, certificate),
    },
  });
}
