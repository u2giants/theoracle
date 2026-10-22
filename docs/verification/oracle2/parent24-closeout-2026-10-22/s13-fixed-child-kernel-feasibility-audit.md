# S13 fixed archive child: read-only feasibility audit

Status: finished read-only proposal, not an implemented or admitted boundary. No child, native command, filter installation, prctl/seccomp experiment, privilege change or host change was performed. Existing loader/runtime/child availability flags remain false. Root retains architecture/security/resource decisions.

## Conclusion

A narrowly sealed fixed Linux parser is technically plausible under a trusted pre-seal bootstrap and trusted kernel/host threat model. Current Oracle has neither that seal nor a qualified fixed child supervisor. Two requirements need explicit root judgment before implementation: the treatment of kernel-provided executable mappings, and whether independently exporting the exact attached kernel BPF bytes is mandatory. The latter is unavailable to the observed unprivileged process. No capability acquisition is proposed.

The boundary would prevent new post-seal opens/native loads and new executable mappings. It cannot retrospectively authenticate code already run during startup, prove parser semantic correctness, protect against a malicious host/same-UID debugger outside the stated boundary, or make a successful archive check restore/serve/dispatch authority.

## Source ownership and reuse

Audited frozen consumer: `/tmp/oracle-parent24-wy02uT/recovery-observe-fixture`, head `5f1e0bc0ca4f4feb6ee7c3f87d0502ed61edcd76`. Production recovery source is unchanged from the preceding reviewed packet.

* `services/oracle-brain/oracle_brain/hosting/forward_recovery.py:27–55` owns existing bounded Docker execution. Its one private subprocess call fixes `/usr/bin/docker`, private stdout, discarded stderr, finite timeout and RLIMIT_FSIZE. It does not implement an archive-child RLIMIT_AS, seccomp/NNP, inherited-three-FD handshake, per-child rusage or installed-runtime enforcement. Its old API must remain unchanged.
* The same file's `_read_private_archive_v1` at line183 and `_verify_replacement_archive_fd_v1` at244 own the existing TAR policy. Current raw TAR parsing uses uncompressed read/stream modes. Reuse this exact policy, not a second archive parser. Its top-level imports include psycopg, runtime/synthetic owners and SSL; importing that whole module into a minimal child needlessly broadens the trusted closure.
* `hosting/restore_receipts.py:16–18` imports Pydantic, the canonical helpers and synthetic fixture. `operating_model/recovery_contracts_v1.py` already owns closed child-control records. Neither authenticates installed execution or provides a process supervisor. A minimal extraction of the existing pure archive policy into one owned module with old same-object forwarders is a separate source decision; it must preserve behavior and existing boundary tests, rather than weaken an import allowlist.

## Actual read-only observation

Retained `/tmp/oracle-parent24-wy02uT/s13-kernel-readonly-observation.json` records Linux7.0.0-38-generic/x86_64, available seccomp actions including kill_process, current CapEff0/NoNewPrivs0/Seccomp0, and personality0. Linux ABI/BPF/audit headers are present. This proves only interface visibility, not permission to install a filter or enforcement success.

The mapping snapshot came from the tool's Python3.14 process, NOT the proposed qualified Python3.13 interpreter. It is descriptive only. It includes ordinary ELF mappings and `[vdso]`/`[vsyscall]` kernel executable mappings. No writable/executable mapping was observed in that snapshot; it is not a complete closure or a substitute for a proposed child's independently installed file/mapping census.

## Exact proposed enforcement boundary

1. Trusted fixed bootstrap reads only bounded control and independently pinned runtime/custody records before any archive content. It fixes interpreter/import roots/environment, hard memory limit and original absolute wall plus monotonic deadline. It preloads the actual parser/crypto closure and verifies exact native backing files, offsets, protections and aliases. Unknown/deleted/memfd/anonymous executable mappings, writable executable pages or writable aliases to executable backing refuse. Loader configuration and startup inputs must be included in the actual independently installed closure; a loaded-module snapshot alone cannot prove what ran earlier.
2. Verify the exact ABI/personality, then set irreversible NNP and install one pinned classic BPF program. Check AUDIT_ARCH_X86_64 AND reject the x32 syscall bit; unknown syscall numbers deny. Arguments require explicit width handling. No TRACE, notification broker, logging-only decision or fallback filter.
3. Conservative post-seal proposal denies ALL mprotect/pkey_mprotect/mremap/personality and executable-map alteration paths, avoiding an incomplete protection-transition policy. Allow mmap only narrowly required private anonymous non-executable allocations with exact flags, no MAP_FIXED/SHARED/file backing/unknown flags, under a verified non-READ_IMPLIES_EXEC personality. Actual allocator viability remains to be proved in a later specifically admitted invented test; no experiment was run here.
4. Reads/pread/lseek/fstat are restricted to the three exact inherited O_RDONLY data FDs. Bounded control stdin is consumed/closed before the seal. Result stdout is bounded closed metadata, stderr remains private and is never relayed as archive content. No dup/FD replacement, descriptor receipt, unlisted inherited FD or path reopen. Permit only narrowly demonstrated allocation/unmap, exact clock, required signal/futex and exit calls. The final complete allowlist is not certified by this audit.
5. Default deny closes open/openat/openat2/creat, exec, fork/vfork/clone/clone3, sockets, ptrace/process-memory paths, io_uring, userfaultfd, bpf/perf, memfd/shared-memory and architecture/protection-changing interfaces. Denying opens after preload makes a new file-backed dlopen/import fail; preventing executable allocations addresses in-memory native-code alternatives. It does not attest pre-seal code.
6. Parent retains the same actual original deadline, current custody and exact three-file tuple/hash checks before/after. One private fixed child branch must enforce memory in the child before A-sized work, independently inspect actual limits and seal state, and own exactly one wait/rusage/kill/reap lifecycle. No public argv/FD/callback or fresh30s capture. Do not add a second generic subprocess engine or change old Docker behavior.

## Concrete readback and trust limits

Linux documents that PTRACE_SECCOMP_GET_FILTER requires CAP_SYS_ADMIN and CONFIG_CHECKPOINT_RESTORE and refuses a filtered caller. The observed process has no capabilities. Therefore exact independent kernel-exported filter-byte readback is a genuine unavailable requirement in this environment; do not infer it from Seccomp2 or filter count, and do not elevate to obtain it.

A potentially admissible alternative FOR ROOT JUDGMENT is a trusted pinned bootstrap constructing exact pinned BPF bytes, observed successful NNP/filter installation, parent inspection of actual NNP1/Seccomp2/filter count, and later actual hostile-open/load/exec/network/memory/timeout refusal proof. That is source-bound installation plus enforcement evidence, not independent bytecode export. If exact export is required, this design stays blocked.

The regular-file runtime manifest cannot silently represent kernel `[vdso]`/`[vsyscall]` mappings. Root must ratify a closed kernel/ABI trust-base rule with actual mapping verification, or refuse them. Do not label these mappings independently hashed ordinary files or equate kernel release strings with full installed qualification.

Seccomp is explicitly not a complete sandbox. In-process parser compromise can use whatever result channel is allowed. Parent must not log rejected output or use a child result to issue source/custody/grant authority; all results retain exact bindings, bounds and quarantined semantics. Interpreter/ELF/loader closure, externally installed resource authority and original currentness remain prerequisites even after a seal exists.

## Minimum subsequent source packet, if root ratifies

One pure extraction of SAME archive validation policy; one fixed entrypoint; one private branch in SAME bounded execution owner; closed ABI/BPF predicates/readbacks and tests. Preserve all old APIs and source manifest all executed closure. First later proof must cover actual complete integrity, unlisted filesystem/import/dlopen/exec/network/extra-FD denial, allocator success under the fixed ceiling, memory exhaustion, original deadline, rollback/late result and exact child cleanup. Source-only tests cannot establish these runtime properties. No actual invocation is authorized by this report.

## Primary evidence

* [Linux seccomp filter documentation](https://docs.kernel.org/userspace-api/seccomp_filter.html): syscall/argument filtering, architecture checks and sandbox limits.
* [Linux no_new_privs documentation](https://docs.kernel.org/userspace-api/no_new_privs.html): irreversible task property, inheritance and limited guarantees.
* [Linux seccomp ABI](https://man7.org/linux/man-pages/man2/seccomp.2.html): x32 ambiguity, argument widths and filter installation.
* [Linux ptrace filter export](https://man7.org/linux/man-pages/man2/ptrace.2.html): exact filter export privilege/configuration requirements.
* [Linux mmap semantics](https://man7.org/linux/man-pages/man2/mmap.2.html) and [mprotect semantics](https://man7.org/linux/man-pages/man2/mprotect.2.html): executable protections, aliases, personality and protection transitions.

These sources support design limits only; none proves this machine has installed or enforced the proposed boundary. Whole S13 consistency, complete current tail, actual restored SQL019 paused state, private/vector custody, serving/dispatch denial, measured RTO/RPO and company acceptance remain distinct open obligations.
