# Root finite candidate argument policy, SOURCE ONLY

This resolves the uncovered source-policy constants in v3. It does not qualify any runtime or permit actual syscalls. Existing kernel/native ABI commitment and default KILL_PROCESS apply first. Pure builder parameters derive solely from the independently installed AS/archive authority; caller-selected rules are prohibited. Unknown variant or an unsupported legitimate runtime remains unavailable.

For the first variant require 4096-byte pages and four-level lower-half user addresses: relevant non-null pointers must be within1..0x00007fffffffffff. This is structural bounds only, never proof of live mappings or memory ownership. Nullable pointers permit zero explicitly below. Relevant scalar arguments compare their FULL64 bits, not low32 only. Unused ABI arguments are ignored, not assigned fictional register values by libc wrappers.

read0/pread6417: fd exactly3/4/5, buffer non-null lower-half pointer, count1..65536; pread offset nonnegative<=installed archive_limit_bytes. write1: fd1/2, buffer same pointer bounds, count1..65536. fstat5: fd3/4/5 and non-null output pointer. lseek8: fd3/4/5, whence0/1/2 with full64 highwords zero; SEEK_SET offset0..archive_limit_bytes; CUR/END signed64 offset within[-archive_limit_bytes,+archive_limit_bytes]. Kernel may still refuse an otherwise structurally admitted offset; no retry authority follows.

clock_gettime228: clock0 or1 only, non-null result pointer. rt_sigreturn15 has no scalar arguments. rt_sigprocmask14: how0/1/2, set and oldset nullable lower-half pointers, sigsetsize exactly8. This does not install handlers or make SIGKILL blockable.

futex202: operation exactly WAIT_PRIVATE128 or WAKE_PRIVATE129, uaddr non-null lower-half pointer aligned4; val0..0x7fffffff full64 highword zero. WAIT timeout mustNULL, uaddr2NULL and val3zero; WAKE unused arguments are ignored. A wait cannot defeat the parent's original absolute deadline/kill/reap. No futex2/bitset/requeue/PI/realtime/robust variants. Pure implementation may expose unsupported-status rather than silently widen these constants.

mmap9: address0; length1..installedAS; prot3 exactly; flags0x22 exactly; fd full64 0xffffffffffffffff; offset0. munmap11: non-null lower-half page-aligned address, length1..installedAS, length page-aligned and address+length<=0x0000800000000000 without wrap. No mapping ownership claim is inferred from these structural checks. Parent stopped mapping census and complete trusted bootstrap remain required; unknown postseal executable mappings are never admitted.

kill62: pid0 exactly and signal19 exactly; parent/child must separately establish pid==pgrp==sid before the one allowed stop; second stop is terminal refusal. exit60/exit_group231: status exactly0(success) or70(fixed failure), full64 highword zero. Fixed source error branch uses70; all other exits/signals refuse parent acceptance.

Source-only evaluations must cover each allow boundary, adjacent denied value, highword confusion, signed limits/overflow, unknown syscall/ABI/x32 and extraFD. BPF byte evaluator must execute emitted bytes independently of any descriptive allow-predicate; tests comparing a helper to itself do not establish encoding. No actual seccomp/prlimit/child/filter effects are authorized.

Primary ABI references: https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/entry/syscalls/syscall_64.tbl ; https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/futex.h ; https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/include/uapi/asm/signal.h . Numbers are candidate Linux x86_64 constants, not current-machine qualification.
