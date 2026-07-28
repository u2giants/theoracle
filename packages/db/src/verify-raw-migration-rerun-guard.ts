import assert from 'node:assert/strict';
import { assertRawMigrationRerunTarget } from './raw-migration-rerun-guard';

assert.throws(
  () =>
    assertRawMigrationRerunTarget({
      url: 'postgres://oracle:oracle@localhost:5432/oracle_fresh',
      optIn: undefined,
    }),
  /ORACLE_MIGRATION_RERUN_TEST=1/,
);
assert.throws(
  () =>
    assertRawMigrationRerunTarget({
      url: 'postgres://oracle:oracle@db.example.com:5432/oracle_fresh',
      optIn: '1',
    }),
  /non-loopback host/,
);
assert.throws(
  () =>
    assertRawMigrationRerunTarget({
      url: 'postgres://oracle:oracle@localhost:5432/team_fresh',
      optIn: '1',
    }),
  /outside oracle_fresh/,
);
for (const host of ['localhost', '127.0.0.1', '[::1]']) {
  const parsed = assertRawMigrationRerunTarget({
    url: `postgres://oracle:oracle@${host}:5432/oracle_fresh`,
    optIn: '1',
  });
  assert.equal(parsed.pathname, '/oracle_fresh');
}

console.log('PASS raw migration rerun write-target guard');
