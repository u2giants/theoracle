"""A new invented worker must never inherit the store's wildcard graph authority."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
SPEC=importlib.util.spec_from_file_location('proof_acl',ROOT/'dev/oracle2/hosting/compile_falkor_proof_acl.py')
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)

class ProofACLTests(unittest.TestCase):
    def source(self):
        return (ROOT/'dev/oracle2/hosting/golden/falkordb-candidate.json').read_bytes()

    def test_preserves_all_original_contracts_except_new_acl(self):
        raw=self.source();before=json.loads(raw)
        after=MODULE.compile_delta(raw,hashlib.sha256(raw).hexdigest())['compose']
        service=after['services']['falkordb'];original=before['services']['falkordb']
        self.assertEqual({k:v for k,v in after.items() if k!='services'}, {k:v for k,v in before.items() if k!='services'})
        self.assertEqual({k:v for k,v in after['services'].items() if k!='falkordb'}, {k:v for k,v in before['services'].items() if k!='falkordb'})
        self.assertEqual({k:v for k,v in service.items() if k not in ('entrypoint','command','environment')}, {k:v for k,v in original.items() if k not in ('entrypoint','command','environment')})
        script='\n'.join(service['entrypoint'])+'\n'+'\n'.join(service.get('command',[]))
        self.assertIn(MODULE.WORKER,script)
        for user,(env,commands) in MODULE.USERS.items():
            line=next(line for line in script.splitlines() if 'echo "user '+user+' ' in line)
            self.assertNotIn('~*',line)
            self.assertIn('~'+MODULE.GRAPH+' ~'+MODULE.GRAPH+'__ontology',line)
            self.assertIn('-@all '+commands,line)
            self.assertNotIn('+@connection',line)
            self.assertIn('"$${#'+env+'}" -eq 64',script)
            self.assertIn(env,script.split('unset FALKORDB_PASSWORD')[1].splitlines()[0])
        executor=next(line for line in script.splitlines() if 'echo "user oracle_native_proof_executor_v1 ' in line)
        self.assertNotIn('+graph.query',executor)
        self.assertNotIn('+graph.list',executor)

    def test_changed_review_input_rejected(self):
        with self.assertRaisesRegex(ValueError,'reviewed compose bytes differ'):
            MODULE.compile_delta(self.source(), '0'*64)

    def test_confirmed_resource_rejected(self):
        raw=(ROOT/'dev/oracle2/hosting/golden/falkordb-confirmed.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'candidate-only'):
            MODULE.compile_delta(raw,hashlib.sha256(raw).hexdigest())

    def test_second_install_refused(self):
        raw=self.source();first=MODULE.compile_delta(raw,hashlib.sha256(raw).hexdigest())
        raw=json.dumps(first['compose']).encode()
        with self.assertRaisesRegex(ValueError,'fresh proof environment required'):
            MODULE.compile_delta(raw,hashlib.sha256(raw).hexdigest())

if __name__=='__main__':unittest.main()
