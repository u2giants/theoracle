const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);

export function assertRawMigrationRerunTarget(args: {
  url: string | undefined;
  optIn: string | undefined;
}): URL {
  if (args.optIn !== '1') {
    throw new Error('ORACLE_MIGRATION_RERUN_TEST=1 is required for this disposable database test.');
  }
  if (!args.url) throw new Error('DIRECT_URL or DATABASE_URL is required.');

  const parsed = new URL(args.url);
  const hostname = parsed.hostname.replace(/^\[|\]$/g, '');
  if (!LOOPBACK_HOSTS.has(hostname)) {
    throw new Error(`Refusing migration rerun fixture on non-loopback host ${parsed.hostname}.`);
  }
  if (parsed.pathname.replace(/^\//, '') !== 'oracle_fresh') {
    throw new Error(`Refusing migration rerun fixture outside oracle_fresh: ${parsed.pathname}.`);
  }
  return parsed;
}
