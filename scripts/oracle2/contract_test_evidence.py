"""Shared mandatory evidence owner for Oracle workflow and phase verification.

The existing algorithm lives here once so the phase frontdoor can remain
standard-library-only while pytest runs in its already-selected locked runtime.
The old verifier retains its import-compatible forwarding entry point.
"""
import hashlib
from xml.etree import ElementTree as ET


def aggregate_evidence(jobs,results,directory):
    combined=ET.Element('testsuites');tests=skips=failures=0;invalid=[]
    if len(results)!=len(jobs):invalid.append('worker population incomplete')
    for job,result in zip(jobs,results):
        output=directory/(job['name']+'.stdout');junit=directory/(job['name']+'.xml')
        result['stdout_sha256']=hashlib.sha256(output.read_bytes()).hexdigest() if output.is_file() else None
        if not output.is_file():invalid.append('required worker output missing')
        result['junit_present']=junit.is_file()
        if result['timed_out'] or result.get('launch_error') or result['exit_code']!=0:invalid.append('worker did not complete successfully')
        if not junit.is_file():invalid.append('required junit evidence missing');continue
        junit.chmod(0o600);raw=junit.read_bytes();result['junit_sha256']=hashlib.sha256(raw).hexdigest()
        try:root=ET.fromstring(raw)
        except ET.ParseError:invalid.append('required junit evidence malformed');continue
        cases=root.findall('.//testcase')
        if not cases:invalid.append('required worker cases missing')
        count_skips=sum(c.find('skipped') is not None for c in cases)
        count_failures=sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
        tests+=len(cases);skips+=count_skips;failures+=count_failures
        result.update(tests=len(cases),skipped=count_skips,failures=count_failures)
        combined.append(root)
    if skips or failures:invalid.append('required synthetic gate failed or skipped')
    return {'tests':tests,'skipped':skips,'failures':failures,'exit_code':int(bool(invalid)),
        'junit_sha256':hashlib.sha256(ET.tostring(combined)).hexdigest(),'worker_results':results,
        'evidence_errors':invalid}
