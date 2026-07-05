#!/usr/bin/env node
import 'dotenv/config';
import postgres from 'postgres';

const sinceHours = Number(process.env.SINCE_HOURS ?? process.argv[2] ?? 48);
const limit = Number(process.env.LIMIT ?? process.argv[3] ?? 50);
const url = process.env.DIRECT_URL;

if (!url) {
  console.error('Missing DIRECT_URL. Point it at the intended database before running.');
  process.exit(1);
}

const sql = postgres(url, { max: 1, prepare: false });

try {
  const failedJobs = await sql`
    SELECT
      trigger_run_id,
      job_type,
      status,
      started_at,
      finished_at,
      error,
      input_json
    FROM job_runs
    WHERE status IN ('failed', 'degraded')
      AND started_at >= now() - (${sinceHours}::text || ' hours')::interval
    ORDER BY started_at DESC
    LIMIT ${limit}
  `;

  const failedAttempts = await sql`
    SELECT
      task_type,
      slot,
      route_id,
      provider,
      model_id,
      is_primary,
      error,
      created_at
    FROM model_run_attempts
    WHERE status = 'failed'
      AND created_at >= now() - (${sinceHours}::text || ' hours')::interval
    ORDER BY created_at DESC
    LIMIT ${limit}
  `;

  console.log(`# Worker Failure Digest\n`);
  console.log(`Window: last ${sinceHours} hours`);
  console.log(`Limit per section: ${limit}\n`);

  console.log(`## Failed job_runs (${failedJobs.length})\n`);
  for (const row of failedJobs) {
    console.log(`- ${row.started_at.toISOString()} ${row.job_type} ${row.status}`);
    console.log(`  - triggerRunId: ${row.trigger_run_id}`);
    if (row.finished_at) console.log(`  - finishedAt: ${row.finished_at.toISOString()}`);
    if (row.error) console.log(`  - error: ${String(row.error).replace(/\s+/g, ' ').slice(0, 800)}`);
    if (row.input_json) console.log(`  - input: ${JSON.stringify(row.input_json).slice(0, 800)}`);
  }
  if (failedJobs.length === 0) console.log('- none');

  console.log(`\n## Failed model_run_attempts (${failedAttempts.length})\n`);
  for (const row of failedAttempts) {
    console.log(`- ${row.created_at.toISOString()} ${row.task_type} slot=${row.slot}`);
    console.log(`  - route: ${row.route_id} (${row.provider}/${row.model_id}) primary=${row.is_primary}`);
    if (row.error) console.log(`  - error: ${String(row.error).replace(/\s+/g, ' ').slice(0, 800)}`);
  }
  if (failedAttempts.length === 0) console.log('- none');
} finally {
  await sql.end();
}
