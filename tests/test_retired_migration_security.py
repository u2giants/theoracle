"""Offline contracts for fresh-database permission coverage (no live DB required)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'packages/db/migrations/sql'


class MigrationSecurityTests(unittest.TestCase):
    def test_every_generated_retired_table_is_locked_down(self):
        created = {
            name
            for path in (ROOT / 'packages/db/migrations').glob('0*.sql')
            for name in re.findall(r'CREATE TABLE "([^"]+)"', path.read_text())
        }
        sql = (RAW / '22_retired_oracle2_lockdown.sql').read_text()
        listed = set(re.findall(r"^    '([^']+)'", sql, re.MULTILINE))
        self.assertEqual(created - {'employees', 'employee_identities'}, listed)
        self.assertIn("IF to_regclass(format('public.%I', retired_table)) IS NOT NULL THEN", sql)
        self.assertIn('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', sql)
        self.assertIn('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC, anon, authenticated', sql)
        self.assertNotIn('DROP TABLE', sql)

    def test_department_policies_follow_creation_and_replay_safely(self):
        name = '63_departments_rls.sql'
        self.assertGreater(name, '61_departments.sql')
        sql = (RAW / name).read_text()
        for table in ('departments', 'employee_departments'):
            self.assertIn(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;', sql)
            for suffix, clause in (
                ('employee_read', 'FOR SELECT TO authenticated\n  USING (public.current_employee_id() IS NOT NULL)'),
                ('admin_all', 'FOR ALL TO authenticated\n  USING (public.current_employee_is_admin())\n  WITH CHECK (public.current_employee_is_admin())'),
            ):
                policy = f'{table}_{suffix}'
                drop = f'DROP POLICY IF EXISTS {policy} ON public.{table};'
                create = f'CREATE POLICY {policy} ON public.{table}\n  {clause};'
                self.assertIn(drop, sql)
                self.assertIn(create, sql)
                self.assertLess(sql.index(drop), sql.index(create))
        self.assertNotIn('TO anon', sql)

    def test_docs_no_longer_promise_macro_recreation(self):
        text = (ROOT / 'docs/agents/11-intentional-quirks.md').read_text()
        self.assertNotIn('A fresh DB still gets those tables', text)
        self.assertIn('Fresh databases no longer receive those hand-SQL-only objects.', text)
        readme = (RAW / 'README.md').read_text()
        for name in ('22_retired_oracle2_lockdown.sql', '63_departments_rls.sql'):
            self.assertIn(name, readme)


if __name__ == '__main__':
    unittest.main()
