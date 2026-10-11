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
store. Never use company stores or default SDK providers. Sanitized reproducible receipt: [W01-execution.json](W01-execution.json). Lock SHA-256: 9cedb786240ce78dac821f92ea2ddb1caa46125632b185a605ea541244403585

The owned-store runner `scripts/oracle2/verify_operating_model_baseline.py` creates
and validates its own pinned synthetic store, archives only the two exact
baselines, requires the unique expected-loss marker after finalize/reload,
rejects any infrastructure marker, records log hashes, then removes only its
newly created ephemeral container. The probe independently validates the Docker
owner label and exact loopback binding; company/recovery ports are forbidden.
No caller-supplied graph target can enter the runner.

W01 fixture tests establish source-inventory consistency only. No production
extractor, quarantine-serving or semantic-coverage proof is claimed until the
new ledger/model gates exist. The boundary component now exists and enforces
only the narrow Oracle helper allowlist; parent-package, dynamic-import and
exec/eval bypasses are denied. SDK/provider/authority contracts remain separately
required.

Runner revision records all boundary test results itself via JUnit, derives
recovery counts from JUnit rather than parsing prose, separates unexpected-pass
from infrastructure failure, records exact executed-file hashes and cleans up
only its own container. Invalid syntax/relative imports return denied records;
all dynamic import/exec/eval spellings tested by the reviewer are now denied.
The import rule permits modules on the listed helper allowlist (including parent
from-import spelling); it does not grant permission for side effects or new
business APIs. Code/release review remains independent of this static check.
