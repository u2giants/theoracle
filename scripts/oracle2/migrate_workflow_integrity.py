#!/usr/bin/env python3
"""Idempotent additive Oracle-only migration; prove exact target before applying."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlparse
import psycopg


def migrate(url: str, *, expected_database: str, expected_host: str, reviewer_report: Path | None = None) -> None:
    parsed = urlparse(url)
    if parsed.hostname != expected_host or parsed.path.lstrip('/') != expected_database:
        raise PermissionError('migration URL does not match exact expected Oracle target')
    if expected_host not in {'localhost','127.0.0.1'}:
        # Production review/gate is an external precondition, never inferred from a text verdict.
        raise PermissionError('hosted migration requires the W11 deployment runner; local runner cannot mutate hosted stores')
    if not expected_database.startswith('oracle_operating_model_test_'):
        raise PermissionError('local migration requires session-owned synthetic database namespace')
    sql = Path(__file__).resolve().parents[2] / 'services/oracle-brain/sql/004_workflow_integrity.sql'
    with psycopg.connect(url) as conn:
        row = conn.execute('SELECT current_database(), inet_server_addr()::text, current_user').fetchone()
        if row[0] != expected_database:
            raise PermissionError('connected database identity changed')
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('oracle2-workflow-integrity-004',))
        conn.execute(sql.read_text())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--expected-host', required=True)
    args=parser.parse_args()
    migrate(os.environ['ORACLE2_TEST_ADMIN_URL'],expected_database=args.expected_database,expected_host=args.expected_host)

if __name__ == '__main__': main()
