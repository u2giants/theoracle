# S13 pure native successor SOURCE — step 9 source gate evidence

Date: 2026-10-27 EDT. Session ses_ffe5e8085a0c2ffedMyHk2RNZm on edge-dev.
Branch: `mimo/parent24-s13-pure-native-source` from upstream main `f65322b0`.
Task class: code. Closeout ledger §6 step 9, source portion only.

## Predecessor worktree check

No partial worktree from the cancelled predecessor was found under C:\tmp\.
The predecessor stalled 39 minutes inside one tool call and left no usable
partial source. Started fresh from current upstream main.

## Composition of ab091 preserved delta

The preserved partial source at commit ab0915761f2c (S13 recovery-child-pure-v2:
PARTIAL, UNTESTED DTO/parser additions over complete 2633 + one TAR-policy
extraction) is FULLY CONTAINED in current upstream main via PR203 (commit
889b42d4, merged 2026-10-23, "Complete closed V2 DTOs and exact classic-BPF
builder/evaluator for S13 fixed child source"). Main is a strict superset of
ab091: additional `bind_descriptive_program` validator, expanded parent
observation docstring, `parse_recovery_archive_enforcement_variant_v2`, and
`terminal_observation` extended to include `'observed'`. No composition was
needed — the additive delta was already merged. No B+C subsets or inverse
old-main was used.

## Source gate results

| Gate item | Result | Evidence |
|---|---|---|
| Closed DTOs complete | PASS | `RecoveryArchiveEnforcementVariantV2`, `RecoveryArchiveRuntimeManifestV2`, `RecoveryArchiveChildRequestV2`, `RecoveryArchiveStructuralFrameV2`, `RecoveryArchiveParentObservationV2` + all parsers in `recovery_contracts_v1.py` |
| SAME manifest variant exact | PASS | `RecoveryArchiveRuntimeManifestV2` extends V1 with explicit v2 protocol, fixed preexec pin, enforcement binding; `fixed_variant` validator enforces exact pins |
| BPF builder bytes deterministic | PASS | `build_classic_bpf_v2` emits deterministic sock_filter image; `BUILDER_IMMEDIATE_INVENTORY` closed set; `classic_bpf_program_sha256` stable |
| Independent byte evaluator | PASS | `evaluate_classic_bpf_v2` executes emitted bytes through classic-BPF VM without loading or consulting allow-predicates; `test_evaluator_executes_bytes_not_a_predicate` verifies |
| Strict variant validators (positive + negative) | PASS | 26 tests: `test_recovery_child_v2_dto.py` (9 tests incl. negatives) + `test_recovery_seccomp_bpf_v2.py` (17 tests incl. negatives). Negative cases: wrong tunables, wrong memory limit, wrong preexec, FD mismatch, noncanonical bytes, hash mismatch, widened parameters, unknown syscalls, high-word adversarial, wrong mmap/munmap/futex/lseek bounds |
| Retained V1 tests pass | PASS | `test_recovery_contracts_v1.py` + `test_recovery_archive_child_contract_v1.py`: 84 passed, 2 pre-existing teardown errors (oversized parametrized id — documented in prior evidence, unrelated) |
| Old APIs still pass | PASS | V1 records/parsers byte-compatible; `test_v1_records_remain_byte_compatible` verifies; no V1 signature changes |
| Flags enable only qualifying exact runtime (pure-checked) | PASS | `Literal[False]` on all four availability/qualification flags; `test_availability_flags_stay_false_on_v2_manifest_fields` + `test_enforcement_variant_pins_closed_constants_and_false_flags` verify; no source record enables any flag |

## Test counts

- `test_recovery_child_v2_dto.py`: 9/9 passed (0 failed, 0 errors)
- `test_recovery_seccomp_bpf_v2.py`: 17/17 passed (0 failed, 0 errors)
- `test_recovery_contracts_v1.py` + `test_recovery_archive_child_contract_v1.py`: 84 passed, 2 pre-existing teardown errors (oversized parametrized id)
- `test_recovery_runtime_manifest_v1.py`: 30 pre-existing failures on Windows (POSIX path/uid validators — identical on unmodified main; Linux-only test suite)

## Runtime/resource PLAN document

`docs/verification/oracle2/s13-pure-native-runtime-resource-plan.md` authored
with complete proof matrix (P1–P26) covering: admission closure, currentness,
ABI, mappings, limits, NNP, filter-count, denied syscalls, high-word,
allocator, exhaustion, original expiry, abort, late frame, second stop, input
mutation, wait4, cleanup + resource budget. PENDING for independent review.

## ACTUAL-runtime proof gate

**PENDING** — explicitly NOT run by this step. No actual child process, filter
install, prlimit, private archive, BPF load, or kernel interaction of any kind
occurred. All P-items in the PLAN document are PENDING.

## No-effects confirmation

Zero effects: no child process, no filter install, no prlimit, no private
archive, no BPF load, no kernel interaction, no database writes, no provider
calls, no production writes, no real Teams, no POP shared-db. Pure source +
pure tests only.
