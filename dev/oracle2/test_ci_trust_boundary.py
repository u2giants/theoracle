"""Offline workflow-policy proof: refuse forks before any private runner allocation."""
from pathlib import Path
import os
import subprocess
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/oracle2-contracts.yml').read_text())
JOBS = WORKFLOW['jobs']


def shell(script, **values):
    return subprocess.run(['bash', '-e', '-c', script], env={**os.environ, **values},
                          capture_output=True, text=True, timeout=5).returncode


class TrustBoundary(unittest.TestCase):
    def test_event_gate_denies_fork_and_unknown_context(self):
        script = JOBS['trusted-context']['steps'][0]['run']
        cases = [('push','refs/heads/main','',True), ('push','refs/heads/other','',False),
                 ('pull_request','refs/pull/1/merge','u2giants/theoracle',True),
                 ('pull_request','refs/pull/1/merge','foreign/theoracle',False),
                 ('pull_request','refs/pull/1/merge','',False),
                 ('workflow_dispatch','refs/heads/main','u2giants/theoracle',False),
                 ('pull_request_target','refs/heads/main','u2giants/theoracle',False),
                 ('unknown','refs/heads/main','u2giants/theoracle',False)]
        for event, ref, head, expected in cases:
            with self.subTest(event=event, head=head):
                result = shell(script, EVENT_NAME=event, EVENT_REF=ref,
                               HEAD_REPOSITORY=head, BASE_REPOSITORY='u2giants/theoracle')
                self.assertEqual(result == 0, expected)

    def test_no_private_runner_before_trust_proof(self):
        gate = JOBS['trusted-context']
        self.assertEqual(gate['runs-on'], 'ubuntu-latest')
        self.assertEqual(len(gate['steps']), 1)
        self.assertNotIn('uses', gate['steps'][0])
        self.assertNotIn('checkout', gate['steps'][0]['run'])
        job = JOBS['oracle2-offline']
        self.assertEqual(job['needs'], 'trusted-context')
        self.assertEqual(job['if'], "(github.event_name == 'push' && github.ref == 'refs/heads/main') || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository)")
        self.assertEqual(job['runs-on'], ['self-hosted','edge-dev3'])
        self.assertEqual(job['steps'][0]['uses'], 'actions/checkout@v4')

    def test_required_result_never_accepts_skipped_or_failed_suites(self):
        result = JOBS['offline-result']
        self.assertEqual(result['name'], 'oracle2-offline')
        self.assertEqual(result['runs-on'], 'ubuntu-latest')
        self.assertEqual(set(result['needs']), {'trusted-context','oracle2-offline'})
        self.assertEqual(result['if'], 'always()')
        self.assertEqual(len(result['steps']), 1)
        script = result['steps'][0]['run']
        for trust in ('success','failure','skipped','cancelled'):
            for suites in ('success','failure','skipped','cancelled'):
                with self.subTest(trust=trust, suites=suites):
                    self.assertEqual(shell(script, TRUST_RESULT=trust, SUITE_RESULT=suites)==0,
                                     trust == suites == 'success')

    def test_metadata_stays_only_in_original_offline_consumer(self):
        for name, job in JOBS.items():
            if name != 'oracle2-offline':
                self.assertNotIn('ORACLE_TARGET_PROFILE', str(job))
        suite_steps = JOBS['oracle2-offline']['steps']
        consumers = [step for step in suite_steps if 'ORACLE_TARGET_PROFILE_JSON' in str(step.get('env',{}))]
        self.assertEqual(len(consumers),1)
        self.assertEqual(consumers[0]['run'],'node dev/oracle2/prepare-ci-target-profile.mjs')
        commands = '\n'.join(step.get('run','') for step in suite_steps)
        for required in ('verify:parity','@oracle/workers typecheck','oracle2-native-config.test.ts',
                         'replacement-contract.test.ts','verify_workflow_integrity.py --stage W10',
                         'verify_phase.py S02','verify_phase.py S03','verify_holistic_browser.py'):
            self.assertIn(required,commands)


if __name__ == '__main__':
    unittest.main()
