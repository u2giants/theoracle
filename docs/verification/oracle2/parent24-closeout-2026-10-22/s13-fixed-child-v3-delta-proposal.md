# Proposed v3 delta after independent v2 debate — ROOT DECISION REQUIRED

This is a source-only DESIGN PROPOSAL, not an approved implementation contract. Root has not ratified the following additions. No source files changed and no child, seccomp/filter/syscall probe, native, SQL, private-original or installation operation occurred. All availability remains false. Preserve complete v2 and prior Muse REQUEST_CHANGES; these additions supersede neither evidence nor existing API.

## Actual debate and independent judgment

Complete requested freeform DeepSeek session `20261022-061721-2132163` succeeded, followed by ONE successful same-session evidence rebuttal. Neither invocation used `--review` or a governed verdict/allocator claim. First response conditionally concurred with the direction but requested clarification. On rebuttal DeepSeek expressly withdrew D1's export-attempt requirement and D5's arbitrary-total allegation, downgraded TSYNC from required to recommended, and corrected its D10/D12 scope claims. This is debate evidence, not formal review or permission.

My disposition: **DeepSeek conceded** the material factual disagreements. I agree with the remaining ownership/ordering concerns below; I do not accept its sentence 'accepted-by-root' as evidence of root ratification. Source inspection and primary documentation support these conclusions, not an executional feasibility result. Exact runtime allocator/IO compatibility remains unknown.

Primary actual kernel implementation: torvalds/linux `kernel/seccomp.c`, observed blob `86cf4460d69eaa8e1c643e479118e29da00aca9d`, `seccomp_get_filter` lines2215–2225 checks CAP_SYS_ADMIN and an unfiltered caller before proceeding, otherwise EACCES. https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/refs/heads/master/kernel/seccomp.c . Authoritative manual: https://www.kernel.org/pub/linux/docs/man-pages/book/man-pages-6.16.pdf PTRACE_SECCOMP_GET_FILTER. No export probe or elevation occurred. This is primary generic kernel semantics, not qualification of the installed kernel build.

## Proposed replacement/additional contract text

### 1. Preserve unavailable export and exact trust claim

The design does not rely on kernel-exported filter bytes. Export requires CAP_SYS_ADMIN and an unfiltered caller; this design neither obtains nor attempts to obtain those privileges. Same UID, ancestry or stopped-child status is insufficient. An export refusal proves nothing about attached filter bytes and never causes privilege acquisition, ptrace escalation, fallback or evidence substitution. `kernel_exported_filter_bytes_verified=false` remains exact. Pinned trusted bootstrap plus actual installation/readbacks and later adversarial proof remain the stated trusted-program/kernel evidence model, not byte attestation.

### 2. Prove group identity BEFORE group-scoped stop

Before seal and before its only permitted group-scoped signal, the trusted child verifies actual pid==pgrp==sid for its independently created new session. Parent verifies the actual child pid/pgrp/session against the exact owned process handle before accepting the stop as a handshake; repeated checks occur at the stop. Group-changing syscalls remain denied after seal. Missing or foreign identity denies before data reads. Termination targets ONLY that verified owned group, never an unverified supplied group number. Parent never signals a group merely because a DTO declares it.

### 3. One terminal waiter and second-stop refusal

The new fixed child branch has one exclusive actual wait4 reaper. Every wait uses original remaining wall+monotonic time; stop-aware nonblocking observation includes WNOHANG and WUNTRACED. Initial expected stop is the sole handshake; any subsequent stop, including after a complete output frame, is refusal/UNKNOWN, then exact group kill and actual reap. A complete canonical frame is insufficient without correct zero exit, original time, currentness and complete cleanup. Popen or another helper must not also consume the wait status/rusage. No cumulative RUSAGE_CHILDREN or invented counters replace per-child wait4.

### 4. Preconstruct IO; avoid normal interpreter finalization

The child enters only the extracted SAME member policy, never the entire `_verify_replacement_archive_fd_v1` wrapper that currently calls fcntl/dup/fdopen/close. All fixed descriptor IO wrappers are created pre-seal with no later duplicate/close path. The successful fixed result path writes the full bounded frame to FD1, explicitly flushes preconstructed buffered output if used, then invokes the fixed immediate exit path without Python finalization, atexit or returning through main. Failure never relaxes the deny rule for close or any other syscall. Any SIGSYS/nonzero/second stop after a frame is refusal; output cannot make it success. Old APIs retain their original fd/dup/close behavior outside this new sealed branch.

No general close allowance is proposed or approved. Actual library error/destructor behavior remains a qualification question; an impossible path is unavailable, not silently repaired by broadening.

### 5. Explicit compatible protocol-v2 authorship

Retain unchanged protocol-v1 parsers and exact old records. In the SAME recovery control/result module define an explicit closed v2 split: child structural frame carries operation/input/descriptor/custody/closure identities and exact structural success only; parent final observation carries the exact child-frame hash plus actual pre-exec/stopped-process hard+soft memory-limit readbacks, actual wait4 exit/signal/rusage and cleanup observations. Child never authors authoritative wait4 fields. Parent observations cannot be accepted from FD1 as child claims. Exact field definitions still require root review before source authoring.

Keep one parser and one arithmetic: successful complete member population/size/hash validation proves total streamed bytes equals the checked sealed inventory sum. That total is not an independent second observation and does not justify changing the verbatim parser. Parent compares sealed identities/totals as consistency checks, not cross-authority attestation.

### 6. Fixed launch mechanism and old owner preservation

Old BoundedDocker grammar/API/timeout enum remains unchanged. The new fixed child branch extends the same bounded execution owner; its immutable original request fence is the deadline authority. It must not borrow old timeout constants, subprocess.run's internal pid-only timeout/reaper, or a Python preexec_fn in a multithreaded server.

A concrete pre-exec hard-limit mechanism is still a ROOT design decision. Proposed direction for review: a fixed, source-pinned, independently installed minimal single-threaded launcher sets exact hard=soft limits/session/FD layout and execs ONLY the pinned interpreter/entrypoint, with no public argv/path/config/callback selector. Its entire native loader closure and source must be included in the same installation manifest. This proposal is NOT permission to add/compile/run/install it, and no such launcher is presently qualified. If root chooses another same-owner mechanism it must close the same threaded-fork and before-exec-limit requirements; no unbounded spawn fallback.

### 7. Pin allocator entry channel and observe VMA constraints

The independently installed variant must fix the exact allocator entry channel and bytes before bootstrap, including arena maximum, mmap threshold, trim threshold and top-pad policy. Candidate direction for ROOT review: one exact installer-pinned allowlisted GLIBC_TUNABLES value, never a request/environment passthrough. Numerical values are not selected or claimed supported by this debate; they require documented supported-build semantics and exact source review. No automatic probing or learning into the policy.

Actual VMA/map-count limit and headroom join AS/RSS/heap/filesystem as separate resource constraints. Parent may read the actual installed limit under the same original resource checks; it never changes sysctl/host settings. Byte headroom does not prove VMA headroom; failure/uncertainty refuses. brk/mremap/mprotect/madvise or extra mmap flags remain denied unless root separately reviews an explicit contract change; none is approved here. Legitimate allocator success/exhaustion is still a future actual qualification, and unsupported remains acceptable refusal.

### 8. Exact pre-seal import path

Under fixed -I -S -B, the app and pydantic/native dependencies require an explicitly source-authored bootstrap that loads ONLY the exact independent installed absolute import-root tuple before seal. No PYTHONPATH, user site, .pth, plugin directory, caller path or environmental fallback. Bootstrap compares installed roots and complete source/native file pins before import, includes every actually loaded native executable backing in closure, and refuses missing/extra/unresolved imports. No public control path/root field is introduced. Postseal opens/imports remain denied.

### 9. Thread/installation/mapping observations without new authority

Keep actual one-thread bootstrap precondition, actual pre-seal task count and parent-side post-seal task census at handshake. TSYNC is a separate unratified defense recommendation, not an already approved flag or a logical requirement if there is truly one trusted thread; it must not substitute for thread-count evidence. No child /proc open is allowed postseal merely to obtain readbacks. Source has exactly one filter-install site; existing inherited filter stacking can only restrict, while later seccomp/prctl calls remain denied.

No change to unknown kernel/mapping/ABI refusal. The exact immutable vdso code commitment must match the independently qualified actual kernel/boot/CPU variant; dynamic vvar remains trusted kernel DATA. Unavailable commitment stays unavailable; do not learn it from current app observations.

### 10. Close order, full closure and bounded work

One explicit bootstrap order: construct/validate wrappers and bounded control/installed metadata ONLY, never inventory/manifest/archive contents; close FD0; set irreversible NNP; install exact pinned filter; parent verifies actual state at the expected stop; only then continue into untrusted inventory/manifest/archive bytes. Do not perform FD census, open /proc or construct wrappers after seal through a hidden syscall exception.

Parent full installed closure remains mandatory. Its finite aggregate bound is a maximum, not an expected workload and not permission to shrink closure. Partition parent full census and child pre-seal loaded-code/import comparisons explicitly; every byte and metadata validation must fit actual resources and original remaining time. Exceeding the bound/time quarantines/refuses rather than dropping files or renewing time. Actual SC_AVPHYS_PAGES is capacity evidence only; it cannot supply the independently installed per-child hard AS ceiling.

## Required future proof, still held

All old APIs and same-function identity; complete valid archives and malformed/error paths; every permitted/denied syscall and highword/ABI/FD/flag boundary (each terminal kill probe in a separate exact admitted process); actual initial and second stops; complete-frame-plus-failed-exit refusal; no finalization; exact parent rusage; real memory/VMA success and exhaustion; late/expiry/rollback/abort; no inherited extra FD/thread/source/code mutation; exact owned group reaping and input/currentness checks. No execution of these checks is authorized by this document.

Whole backup/restore, consistent cut/current tail, SQL019 paused state, private vectors/model/license, once/cost liabilities, RTO/RPO, installation and company/business use remain distinct open gates.
