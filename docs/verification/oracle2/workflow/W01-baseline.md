# W01 executed baseline

Executed October 11, 2026 EDT on CPython 3.12.14 and SDK 1.4.0.
Main 3bad33583787316d9fdddc3fd45a737b1236b4b1; recovery
36e91038ee6b1126f9d9c27adce7583a6b74c654.
See [boundary](W01-replacement-boundary.md); independent review pending.

## Executed results

- Boundary and independent fixture inventory: 4 passed, zero skipped.
- Old-list loss probe at both frozen baselines: 1 failed each at intended assertion
  after actual SDK build, finalize and reviewed snapshot reload. Each returns zero
  ReportedFinding records where two are required. Exact assertion:
  `nonempty missing_information/conflicts lost after actual SDK finalize/reload`.
  Environment or setup failures are never counted as the red defect proof.
- Pinned recovery focused and real SDK tests: 34 passed, zero skipped, including
  repeated authorization routes, parallel distinct claims, per-original
  observations, alias supports and actual finalize/reload.
- New ledger/projection parity remains W02/W03, not established here.

Exclusively owned ephemeral loopback FalkorDB v4.20.7 uses the repository-pinned
image. No recovery store/volume is modified. Every source/model response is
invented and fixed. Zero paid-provider/private-original/credential calls.

## Reproduction

`evals/oracle2/workflow/legacy_loss_probe.py` is intentionally red; excluded
from normal tests. Archive each exact baseline service into session scratch;
set BASELINE_ROOT and PYTHONPATH to the archive and provide an exclusively owned
ORACLE2_TEST_FALKORDB_URL. Run the probe with the frozen installed interpreter.
Verify the assertion, not merely nonzero exit. Run the archived recovery tests
`test_holistic_graphrag.py` and `test_holistic_graphrag_integration.py` on that
store. Never use company stores or default SDK providers. Raw synthetic receipts
remain local. Lock SHA-256: 9cedb786240ce78dac821f92ea2ddb1caa46125632b185a605ea541244403585
