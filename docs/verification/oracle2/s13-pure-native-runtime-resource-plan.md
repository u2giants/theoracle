# S13 pure native successor — independent full runtime/resource PLAN

Status: PLAN ONLY. No actual child process, filter install, prlimit, private
archive, BPF load, or kernel interaction has been performed or authorized by
this document. Every proof item below is PENDING until a later step executes
the ACTUAL-runtime proof gate under independent review and root release.

Owner context: parent #24, issue #27. Closeout ledger §6 step 9.
Source freeze: `mimo/parent24-s13-pure-native-source` branch on current
upstream main. Source-only V2 DTOs/BPF/evaluator were merged via PR203
(commit 889b42d4). This plan is the prerequisite the later runtime step must
have reviewed and approved BEFORE any actual effects.

---

## 1. Purpose and boundary

This plan defines the proof matrix and resource budget for the actual-runtime
qualification of the S13 fixed native archive child. It covers what must be
demonstrated, measured, and verified when the child actually executes — not
before. The source-only step (this step) has produced pure code and pure tests
with zero effects. This plan does not itself authorize execution.

Invariant carried forward: flags `enforcement_qualified`,
`kernel_exported_filter_bytes_verified`, `native_loader_available`, and
`archive_child_available` remain `Literal[False]` until a qualifying exact
runtime is independently demonstrated. No source record enables them.

---

## 2. Resource budget

| Resource | Budget | Rationale |
|---|---|---|
| Shared deadline | 120 seconds (whole run) | W10 SAME contract; never weakened |
| Per-request deadline | ≤30 seconds | Original wall+monotonic bound; a later read lease cannot extend a phase |
| Worker count | ≤10 | W10 SAME contract |
| Memory (RLIMIT_AS) | 1 GiB (exact `installed_as`) | Fixed at installation; preexec/stopped readbacks must all match |
| CPU (RLIMIT_CPU) | 1 CPU | Fixed at installation |
| File descriptors | `bootstrap_nofile_limit` ∈ [6, 1024] | Set at installation; ABI FDs 3/4/5 reserved for archive/inventory/manifest |
| Bootstrap output | 65536 bytes (exact) | Bounded stdout/stderr capture |
| File count | 1..4096 (sealed archive population) | Closed DTO bound |
| Sealed population total bytes | 1..1 GiB | Closed DTO bound |
| BPF program size | Exact emitted sock_filter image; hash-pinned in enforcement variant | Deterministic builder output; no runtime construction |

**W10-SAME-WORKER-FIT** is an ACCEPTED standing gap. The 120-second / ten-worker
budget is never weakened, cut, or raised to accommodate it.

---

## 3. Proof matrix — every item is PENDING until actual runtime

Each row must be demonstrated under the actual runtime with real kernel
interactions. "Pure-checked" means the source/tests already enforce the
structural precondition; the actual runtime must confirm the kernel honors it.

### 3.1 Admission and closure

| ID | Proof item | What must be shown | Pure-checked precondition |
|---|---|---|---|
| P1 | Admission closure | The child is admitted only when all closed-dto bindings (operation, descriptor, custody, installation, runtime closure, enforcement variant) match exactly the installed manifest | `RecoveryArchiveChildRequestV2.bind_descriptive_installation` raises on any mismatch |
| P2 | Currentness | The original wall and monotonic deadlines are enforced before and after every phase; expired original windows never admit | Request records carry `original_deadline` bounded by `valid_from < original_deadline ≤ min(expires_at, original_horizon)` |
| P3 | ABI | Inherited FDs 3/4/5 are the exact archive/inventory/manifest data ABI; no other inherited FD is used | `fixed_descriptors` validator enforces (3,4,5) |
| P4 | Mappings | The vDSO code hash, kernel mapping policy hash, and interpreter/glibc build hashes match the enforcement variant exactly | Enforcement variant pins all four SHA fields |
| P5 | Limits | Preexec and stopped RLIMIT_AS hard and soft are identical to `installed memory_limit_bytes`; four readbacks agree | `one_waiter_outcome` validator enforces all four equal |
| P6 | NNP | No New Privileges is set (PR_SET_NO_NEW_PRIVS before filter install) | Runtime step must verify via prctl readback; no source record claims it |
| P7 | Filter-count | Exactly one seccomp filter is attached; no additional filters | Runtime step must verify via `/proc/self/status` Seccomp_filters or seccomp(SECCOMP_GET_ACTION_AVAIL); `kernel_exported_filter_bytes_verified` stays FALSE until kernel export confirms |
| P8 | Denied syscalls | Every syscall outside the closed dispatch set is killed (SECCOMP_RET_KILL_PROCESS) | BPF evaluator tests assert default-kill; runtime must confirm with actual denied-syscall probe under the installed filter |
| P9 | High-word | Full 64-bit argument checks (high and low words) reject arguments with nonzero high words outside allowed ranges | `_u64_eq`, `_u64_range`, `_nonzero`, `_nullable` all check both words; tests cover high-word adversarial cases |
| P10 | Allocator | glibc tunables are exactly the independently installed channel: `arena_max=1:mmap_threshold=0:trim_threshold=18446744073709551615:top_pad=0` | `RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2` constant; validator refuses any other string |
| P11 | Exhaustion | Memory exhaustion under RLIMIT_AS is handled: allocation failure never exceeds budget; the process terminates cleanly | Runtime must exercise allocation near limit and confirm bounded behavior |
| P12 | Original expiry | An expired original deadline prevents admission; no renewal, reissue, or replay | Request validator enforces deadline bound; runtime must confirm with expired-seal test |
| P13 | Abort | A mid-operation abort leaves no partial effects beyond the declared sealed population; cleanup is exact | `exact_cleanup_verified` on parent observation; runtime must confirm post-abort state |
| P14 | Late frame | A structural frame arriving after the parent observation deadline is refused (not silently accepted) | Runtime must demonstrate late-frame rejection timing |
| P15 | Second stop | A second stop signal after the first wait4 outcome is handled idempotently; no double-free or state corruption | `one_waiter_outcome` enforces exclusive terminal outcome; runtime must confirm |
| P16 | Input mutation | Mutating any input (archive, inventory, manifest bytes) after admission is detected before use | SHA-pinned triplet binding in `bind_descriptive_request`; runtime must confirm mutation detection |
| P17 | wait4 | Exactly one actual wait4 returns a terminal outcome (exit code OR term signal, exclusive); rusage is captured | `one_waiter_outcome` validator enforces exclusivity; runtime must confirm |
| P18 | Cleanup | After terminal outcome, owned resources (project, container, network, volumes) are independently verified absent | `exact_cleanup_verified` boolean; runtime must confirm via independent absence check |

### 3.2 Enforcement variant validation (pure-checked)

| ID | Proof item | Status |
|---|---|---|
| P19 | Variant positive: exact enforcement variant constructs and binds to request | PASS (pure test) |
| P20 | Variant negative: wrong glibc tunables refused | PASS (pure test) |
| P21 | Variant negative: wrong memory limit refused | PASS (pure test) |
| P22 | Variant negative: wrong preexec executable refused | PASS (pure test) |
| P23 | Variant negative: preexec colliding with interpreter/entrypoint refused | PASS (pure test) |
| P24 | Variant negative: noncanonical BPF byte image refused | PASS (pure test) |
| P25 | Variant negative: BPF hash mismatch refused | PASS (pure test) |
| P26 | Flags stay FALSE: no source record sets `enforcement_qualified`, `kernel_exported_filter_bytes_verified`, `native_loader_available`, or `archive_child_available` | PASS (pure test + Literal[False] types) |

---

## 4. Execution conditions for the later runtime step

Before ANY actual child/filter/prlimit/private archive:

1. This plan must receive independent review and APPROVE (different-engine
   reviewer per reviewer-rotation rules; observation-week freeze applies to
   toolkit PRs only — ordinary theoracle code needs no GitHub review per owner
   ruling 2026-10-15, but the runtime step itself needs an assigned AI
   reviewer's explicit APPROVE on the exact inputs for production actions).
2. Root one-run decision must name the exact step, inputs, and cleanup owner.
3. Fresh source import of ENTIRE 2633 additive delta on current upstream main
   (already composed by the sibling SQL-repair step; verify no drift).
4. The 27 actual cases remain unchanged; no case may be weakened, cut, or
   budget raised.
5. W10 SAME contract unchanged: shared 120s / ten workers / per-request ≤30s /
   full mandatory population / 0 F/E/S/timeout/launch/cleanup.

---

## 5. What this plan does NOT do

- Does not authorize any child process, filter install, prlimit, private
  archive, BPF load, or kernel interaction.
- Does not set any flag to True.
- Does not claim any proof item in §3 is done.
- Does not weaken W10, raise budgets, or cut cases.
- Does not quote synthetic RTO/RPO figures (1.275s RTO / 0.0s RPO / 1.511s
  exposure) as production — those are test/exercise-only figures.
- Does not touch real Teams, company originals, production, or POP shared-db.

---

## 6. Actual-runtime proof gate (explicitly PENDING)

The ACTUAL-runtime proof gate is NOT run by the source-only step. Every P-item
in §3 is PENDING. The gate requires actual admitted closure/currentness/ABI/
mappings/limits/NNP/filter-count/denied-syscalls/high-word/allocator/
exhaustion/original-expiry/abort/late-frame/second-stop/input-mutation/wait4/
cleanup proof — all under full runtime qualification with independent review.
