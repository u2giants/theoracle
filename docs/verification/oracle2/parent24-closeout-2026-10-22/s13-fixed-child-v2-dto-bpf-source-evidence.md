# S13 fixed native archive child — V2 DTO + classic-BPF source evidence

Source-only preservation. No child, filter, prlimit, private-archive, or
syscall experiment occurred. `kernel_exported_filter_bytes_verified` stays
FALSE. Availability flags stay FALSE. Source alone never enables flags or
authorizes a child.

## Field-by-field v3 / v4 compliance (closed V2 DTOs)

Three distinct objects remain distinct protocols in
`services/oracle-brain/oracle_brain/operating_model/recovery_contracts_v1.py`:

| Object | Protocol | v3 binding | Authorization booleans |
|---|---|---|---|
| `RecoveryArchiveChildRequestV2` | `oracle-recovery-archive-check-v2` | operation/descriptor/custody/installation/closure/enforcement-variant hashes; FDs 3/4/5; original wall+monotonic ends; installed memory limit | none claimed |
| `RecoveryArchiveStructuralFrameV2` | `oracle-recovery-archive-structural-v2` | same identities + checked triplet hashes + file_count + sealed_population_total_bytes + structural_success only | source/serve/dispatch/retry all FALSE |
| `RecoveryArchiveParentObservationV2` | `oracle-recovery-archive-parent-observation-v2` | child-frame SHA, preexec/stopped hard+soft AS, one exclusive wait4 exit/signal/rusage, currentness, cleanup | source/serve/dispatch/retry all FALSE |

`RecoveryArchiveRuntimeManifestV2` is the SAME manifest owner with explicit v2
variant: fixed preexec (prlimit) executable pin, installed roots/import paths,
kernel/mapping/allocator/enforcement commitments, resource evidence.
`native_loader_available` and `archive_child_available` remain FALSE.

`RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2` is exactly
`arena_max=1, mmap_threshold=0, trim_threshold=18446744073709551615, top_pad=0`.
Root corrected preliminary trim 0; unsigned max 18446744073709551615 is kept so
automatic arena trimming cannot introduce forbidden brk.

V1 request/result/parsers are unchanged and byte-compatible (retained tests
pass). No second parser or TAR policy.

## Builder constants inventory (root v4 only, no widening)

Module: `services/oracle-brain/oracle_brain/operating_model/recovery_seccomp_bpf_v2.py`.

Syscall numbers emitted as dispatch immediates: 0 read, 1 write, 5 fstat,
8 lseek, 9 mmap, 11 munmap, 14 rt_sigprocmask, 15 rt_sigreturn, 17 pread64,
60 exit, 62 kill, 202 futex, 228 clock_gettime, 231 exit_group.

Argument constants: FDs 3/4/5 (read-family) and 1/2 (write); counts 1..65536;
pointers 1..0x00007fffffffffff (nullable allows 0); SEEK whence 0/1/2;
SEEK_SET offset 0..archive_limit; CUR/END signed offset in
[-archive_limit, +archive_limit]; clock 0/1; rt_sigprocmask how 0/1/2 and
sigsetsize 8; futex WAIT_PRIVATE 128 / WAKE_PRIVATE 129 with val 0..0x7fffffff
and WAIT timeout/uaddr2/val3 NULL; mmap addr 0, length 1..installedAS, prot 3,
flags 0x22, fd 0xffffffffffffffff, offset 0; munmap page-aligned non-null
lower-half address and page-aligned length 1..installedAS with
address+length <= 0x0000800000000000; kill pid 0 signal 19; exit/exit_group
status 0 or 70.

Architecture gate: `AUDIT_ARCH_X86_64 = 3221225534` before any syscall number.
x32 numbers (`0x40000000` bit) kill. Unknown syscall kills. Default action is
`SECCOMP_RET_KILL_PROCESS = 0x80000000`. Full 64-bit argument checks (high and
low words), not low32 only.

`BUILDER_IMMEDIATE_INVENTORY` is the closed set of immediates the builder may
emit. Tests assert dispatch immediates equal exactly the v4 syscall set.

## Evaluator independence (static)

`evaluate_classic_bpf_v2(program_bytes, seccomp_data)` is a classic-BPF VM.
It only:

1. validates the sock_filter byte image length and opcode inventory,
2. decodes `code/jt/jf/k` per 8-byte instruction (`u16 code, u8 jt, u8 jf, u32 k`),
3. steps LD/ST/ALU/JMP/RET against a 64-byte seccomp_data image.

It never imports, calls, or compares against any builder policy helper or
allow-predicate. Tests feed the evaluator raw emitted bytes plus constructed
seccomp_data and assert ALLOW/KILL; a corrupted opcode byte is refused by the
VM rather than re-evaluated as a policy. Self-comparison of a predicate to
itself is not used.

## Tests run

`services/oracle-brain/tests/test_recovery_seccomp_bpf_v2.py` and
`test_recovery_child_v2_dto.py` plus retained
`test_recovery_contracts_v1.py` and `test_recovery_archive_child_contract_v1.py`:
**110 passed** (2 pre-existing setup errors on an oversized parametrized id in
the retained contracts suite; unrelated to this change). Retained V1 tests pass
without effects.

## What remains (not claimed here)

Actual admitted closure/ABI/mappings/limits/NNP/filter-count/deniedsyscalls
proof, highword adversarial enforcement, allocator/exhaustion qualification,
original expiry/abort/late-frame/second-stop/input-mutation/wait4/cleanup proof
under full runtime qualification. Independent full runtime/resource plan and
root one-run decision precede any actual child/filter/prlimit/private archive.
Flags enable only on a qualifying exact runtime. Kernel-exported filter bytes
remain unverified. No privileged probe. Business-acceptance hold is separate.
