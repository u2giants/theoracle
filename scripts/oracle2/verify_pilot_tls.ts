// Actual owned TLS/SCRAM fixture regression; no production connection allowed.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer, connect, type Socket } from 'node:net';
import { pilotPostgres } from '../../apps/web/lib/oracle2-postgres';

async function main() {
  const url = process.env.ORACLE2_TEST_ADMIN_URL;
  assert(url, 'owned fixture URL required');
  const parsed = new URL(url);
  assert.equal(parsed.hostname, '127.0.0.1');
  assert.equal(parsed.username, 'oracle2_admin');
  assert.equal(parsed.pathname, '/oracle2');
  assert.equal(parsed.searchParams.get('sslmode'), 'verify-full');
  const proof = JSON.parse(readFileSync(process.env.ORACLE2_TEST_TLS_QUALIFICATION!, 'utf8'));
  assert(proof.synthetic_only && proof.tls_verify_full && proof.plaintext_refused);
  const sql = pilotPostgres(url);
  try {
    const rows = await sql`select ssl from pg_stat_ssl where pid=pg_backend_pid()`;
    assert.equal(rows[0].ssl, true);
  } finally { await sql.end({ timeout: 1 }); }

  async function refuse(target: URL) {
    const db = pilotPostgres(target.toString());
    try { await assert.rejects(db`select 1`); }
    finally { await db.end({ timeout: 1 }); }
  }
  const badPassword = new URL(url); badPassword.password = 'deliberately-invalid';
  await refuse(badPassword);
  const badCA = new URL(url); badCA.searchParams.set('sslrootcert', '/etc/ssl/certs/ca-certificates.crt');
  await refuse(badCA);
  const weak = new URL(url); weak.searchParams.set('sslmode', 'require');
  assert.throws(() => pilotPostgres(weak.toString()));
  const system = new URL(url); system.searchParams.set('sslrootcert', 'system');
  await refuse(system);
  system.searchParams.set('sslmode', 'require');
  assert.throws(() => pilotPostgres(system.toString()));
  const missingCA = new URL(url); missingCA.searchParams.delete('sslrootcert');
  await refuse(missingCA);

  // Tunnel to the same actual TLS server using an address absent from its SAN.
  const sockets = new Set<Socket>();
  const proxy = createServer((downstream) => {
    const upstream = connect({ host: parsed.hostname, port: Number(parsed.port) });
    for (const socket of [downstream, upstream]) {
      sockets.add(socket);
      socket.on('close', () => sockets.delete(socket));
      socket.on('error', () => { downstream.destroy(); upstream.destroy(); });
    }
    downstream.pipe(upstream); upstream.pipe(downstream);
  });
  await new Promise<void>((resolve, reject) => {
    proxy.once('error', reject); proxy.listen(0, '127.0.0.2', resolve);
  });
  try {
    const address = proxy.address(); assert(address && typeof address !== 'string');
    const wrongHost = new URL(url); wrongHost.hostname = '127.0.0.2'; wrongHost.port = String(address.port);
    await refuse(wrongHost);
  } finally {
    for (const socket of sockets) socket.destroy();
    await new Promise<void>((resolve) => proxy.close(() => resolve()));
  }
  console.log('Pilot TLS: real verified connection; wrong password, CA, hostname and weakened mode refused');
}
main().catch(() => { console.error('Pilot TLS regression failed'); process.exitCode = 1; });
