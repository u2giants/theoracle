"""Pure classic-BPF builder/evaluator tests. No seccomp, prlimit, child or filter effects."""
import pytest
from oracle_brain.operating_model.recovery_seccomp_bpf_v2 import *


def build(installed_as=64 * 1024 * 1024, archive_limit=30):
    return build_classic_bpf_v2(installed_as=installed_as, archive_limit_bytes=archive_limit)


def run(insns, **kw):
    return evaluate_classic_bpf_v2(sock_filter_bytes(insns), seccomp_data_bytes(**kw))


def allowed(insns, **kw):
    return run(insns, **kw) == SECCOMP_RET_ALLOW


def killed(insns, **kw):
    return run(insns, **kw) == SECCOMP_RET_KILL_PROCESS


def test_builder_emits_only_closed_inventory_and_arch_gate_first():
    insns = build()
    raw = sock_filter_bytes(insns)
    assert len(raw) % 8 == 0 and len(insns) > 40
    assert insns[0] == (BPF_LD_W_ABS, 0, 0, OFF_ARCH)
    assert insns[1][0] == BPF_JMP_JEQ_K and insns[1][3] == AUDIT_ARCH_X86_64
    for code, _jt, _jf, k in insns:
        assert code in BPF_ALLOWED_OPCODES
        assert k in BUILDER_IMMEDIATE_INVENTORY or k <= 0xFFFFFFFF
    # every syscall immediate is one of the closed v4 numbers
    syscall_immediates = {k for code, _jt, _jf, k in insns if code == BPF_JMP_JEQ_K and k in (
        SYS_READ, SYS_WRITE, SYS_FSTAT, SYS_LSEEK, SYS_MMAP, SYS_MUNMAP,
        SYS_RT_SIGPROCMASK, SYS_RT_SIGRETURN, SYS_PREAD64, SYS_EXIT, SYS_KILL,
        SYS_FUTEX, SYS_CLOCK_GETTIME, SYS_EXIT_GROUP, AUDIT_ARCH_X86_64,
        EXIT_SUCCESS_STATUS, EXIT_FAILURE_STATUS, SIGSTOP, SIGSETSIZE,
        FUTEX_WAIT_PRIVATE, FUTEX_WAKE_PRIVATE, PROT_READ_WRITE, MAP_PRIVATE_ANONYMOUS,
        0, 1, 2, 3, 4, 5, 8, SEEK_SET,
    )}
    assert SYS_READ in syscall_immediates and SYS_EXIT_GROUP in syscall_immediates
    # prologue is arch/x32 gates then exactly the closed dispatch JEQ+JA pairs
    dispatch_ks = set()
    for code, jt, jf, k in insns[6:34]:
        if code == BPF_JMP_JEQ_K:
            dispatch_ks.add(k)
    assert dispatch_ks == {
        SYS_READ, SYS_WRITE, SYS_FSTAT, SYS_LSEEK, SYS_MMAP, SYS_MUNMAP,
        SYS_RT_SIGPROCMASK, SYS_RT_SIGRETURN, SYS_PREAD64, SYS_EXIT, SYS_KILL,
        SYS_FUTEX, SYS_CLOCK_GETTIME, SYS_EXIT_GROUP,
    }


def test_default_and_unknown_paths_kill():
    insns = build()
    assert killed(insns, nr=999)          # unknown syscall
    assert killed(insns, nr=SYS_READ, arch=0x40000003)  # compat i386
    assert killed(insns, nr=SYS_READ | X32_SYSCALL_BIT)  # x32 number
    assert killed(insns, nr=2)            # open-style unknown


def test_read_boundaries_full64():
    insns = build()
    assert allowed(insns, nr=SYS_READ, args=(3, 0x1000, 1, 0, 0, 0))
    assert allowed(insns, nr=SYS_READ, args=(4, 0x7FFFFFFFFFFF, 65536, 0, 0, 0))
    assert allowed(insns, nr=SYS_READ, args=(5, 1, 1, 0, 0, 0))
    # denied fds
    assert killed(insns, nr=SYS_READ, args=(0, 0x1000, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(2, 0x1000, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(6, 0x1000, 1, 0, 0, 0))
    # highword confusion on fd
    assert killed(insns, nr=SYS_READ, args=(3 | (1 << 32), 0x1000, 1, 0, 0, 0))
    # null / out-of-range buffer
    assert killed(insns, nr=SYS_READ, args=(3, 0, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(3, 0x800000000000, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(3, 0x1000, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(3, 0x1000, 65537, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(3, 0x1000, 1 | (1 << 32), 0, 0, 0))


def test_pread64_offset_is_bounded_and_nonnegative():
    insns = build(archive_limit=30)
    assert allowed(insns, nr=SYS_PREAD64, args=(3, 0x1000, 1, 0, 0, 0))
    assert allowed(insns, nr=SYS_PREAD64, args=(3, 0x1000, 1, 30, 0, 0))
    assert killed(insns, nr=SYS_PREAD64, args=(3, 0x1000, 1, 31, 0, 0))
    assert killed(insns, nr=SYS_PREAD64, args=(3, 0x1000, 1, 1 << 32, 0, 0))
    # negative offset
    assert killed(insns, nr=SYS_PREAD64, args=(3, 0x1000, 1, 0xFFFFFFFFFFFFFFFF, 0, 0))


def test_write_requires_stdout_or_stderr():
    insns = build()
    assert allowed(insns, nr=SYS_WRITE, args=(1, 0x1000, 1, 0, 0, 0))
    assert allowed(insns, nr=SYS_WRITE, args=(2, 0x1000, 65536, 0, 0, 0))
    assert killed(insns, nr=SYS_WRITE, args=(3, 0x1000, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_WRITE, args=(0, 0x1000, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_WRITE, args=(1, 0x1000, 0, 0, 0, 0))


def test_lseek_seek_set_and_signed_cur_end():
    insns = build(archive_limit=30)
    assert allowed(insns, nr=SYS_LSEEK, args=(3, 0, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_LSEEK, args=(3, 30, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_LSEEK, args=(3, 31, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_LSEEK, args=(3, 0xFFFFFFFFFFFFFFFF, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_LSEEK, args=(3, 0xFFFFFFFFFFFFFFE2, 1, 0, 0, 0))  # -30
    assert allowed(insns, nr=SYS_LSEEK, args=(3, 30, 2, 0, 0, 0))
    assert killed(insns, nr=SYS_LSEEK, args=(3, 0xFFFFFFFFFFFFFFE1, 1, 0, 0, 0))  # -31
    assert killed(insns, nr=SYS_LSEEK, args=(3, 0, 3, 0, 0, 0))
    assert killed(insns, nr=SYS_LSEEK, args=(6, 0, 0, 0, 0, 0))
    # whence highword must be zero
    assert killed(insns, nr=SYS_LSEEK, args=(3, 0, 1 | (1 << 32), 0, 0, 0))


def test_fstat_clock_and_sigreturn():
    insns = build()
    assert allowed(insns, nr=SYS_FSTAT, args=(3, 0x1000, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_FSTAT, args=(3, 0, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_FSTAT, args=(1, 0x1000, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_CLOCK_GETTIME, args=(0, 0x1000, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_CLOCK_GETTIME, args=(1, 0x1000, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_CLOCK_GETTIME, args=(2, 0x1000, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_RT_SIGRETURN, args=(0, 0, 0, 0, 0, 0))


def test_rt_sigprocmask_how_and_sigsetsize():
    insns = build()
    assert allowed(insns, nr=SYS_RT_SIGPROCMASK, args=(0, 0, 0, 8, 0, 0))
    assert allowed(insns, nr=SYS_RT_SIGPROCMASK, args=(2, 0x1000, 0x2000, 8, 0, 0))
    assert killed(insns, nr=SYS_RT_SIGPROCMASK, args=(3, 0, 0, 8, 0, 0))
    assert killed(insns, nr=SYS_RT_SIGPROCMASK, args=(0, 0, 0, 4, 0, 0))
    assert killed(insns, nr=SYS_RT_SIGPROCMASK, args=(0, 0x800000000000, 0, 8, 0, 0))


def test_mmap_is_null_private_anonymous_rw_only():
    insns = build(installed_as=64 * 1024 * 1024)
    assert allowed(insns, nr=SYS_MMAP, args=(0, 4096, PROT_READ_WRITE, MAP_PRIVATE_ANONYMOUS, FD_INVAL64, 0))
    assert allowed(insns, nr=SYS_MMAP, args=(0, 64 * 1024 * 1024, 3, 0x22, 0xFFFFFFFFFFFFFFFF, 0))
    assert killed(insns, nr=SYS_MMAP, args=(0x1000, 4096, 3, 0x22, FD_INVAL64, 0))  # non-NULL addr
    assert killed(insns, nr=SYS_MMAP, args=(0, 0, 3, 0x22, FD_INVAL64, 0))
    assert killed(insns, nr=SYS_MMAP, args=(0, 64 * 1024 * 1024 + 1, 3, 0x22, FD_INVAL64, 0))
    assert killed(insns, nr=SYS_MMAP, args=(0, 4096, 1, 0x22, FD_INVAL64, 0))  # prot not RW
    assert killed(insns, nr=SYS_MMAP, args=(0, 4096, 3, 0x21, FD_INVAL64, 0))  # flags not 0x22
    assert killed(insns, nr=SYS_MMAP, args=(0, 4096, 3, 0x22, 0, 0))  # fd not -1
    assert killed(insns, nr=SYS_MMAP, args=(0, 4096, 3, 0x22, FD_INVAL64, 4096))


def test_munmap_page_aligned_and_sum_bounded():
    insns = build(installed_as=64 * 1024 * 1024)
    assert allowed(insns, nr=SYS_MUNMAP, args=(0x1000, 4096, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_MUNMAP, args=(0x1000, 64 * 1024 * 1024, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_MUNMAP, args=(0, 4096, 0, 0, 0, 0))  # null
    assert killed(insns, nr=SYS_MUNMAP, args=(0x1001, 4096, 0, 0, 0, 0))  # not page aligned
    assert killed(insns, nr=SYS_MUNMAP, args=(0x1000, 4095, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_MUNMAP, args=(0x1000, 0, 0, 0, 0, 0))
    # sum exactly at lower-half end is allowed only for zero low word
    assert allowed(insns, nr=SYS_MUNMAP, args=(0x7FFFFFFFF000, 0x1000, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_MUNMAP, args=(0x7FFFFFFFF000, 0x2000, 0, 0, 0, 0))


def test_futex_private_wait_and_wake_only():
    insns = build()
    assert allowed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAIT_PRIVATE, 1, 0, 0, 0))
    assert allowed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAKE_PRIVATE, 0x7FFFFFFF, 0x1234, 0x2345, 0x3456))
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, 128 | 0x10, 1, 0, 0, 0))  # no non-private
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, 0, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_FUTEX, args=(0x1001, FUTEX_WAIT_PRIVATE, 1, 0, 0, 0))  # unaligned
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAIT_PRIVATE, 1, 1, 0, 0))  # WAIT timeout not NULL
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAIT_PRIVATE, 1, 0, 1, 0))
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAIT_PRIVATE, 1, 0, 0, 1))
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAIT_PRIVATE, 0x80000000, 0, 0, 0))
    assert killed(insns, nr=SYS_FUTEX, args=(0x1000, FUTEX_WAIT_PRIVATE, 1 | (1 << 32), 0, 0, 0))


def test_exit_kill_and_status():
    insns = build()
    assert allowed(insns, nr=SYS_EXIT, args=(0, 0, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_EXIT, args=(70, 0, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_EXIT_GROUP, args=(0, 0, 0, 0, 0, 0))
    assert allowed(insns, nr=SYS_EXIT_GROUP, args=(70, 0, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_EXIT, args=(1, 0, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_EXIT, args=(71, 0, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_EXIT, args=(0 | (1 << 32), 0, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_EXIT_GROUP, args=(255, 0, 0, 0, 0, 0))


def test_kill_is_only_self_stop():
    insns = build()
    assert allowed(insns, nr=SYS_KILL, args=(0, SIGSTOP, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_KILL, args=(1, SIGSTOP, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_KILL, args=(0, 9, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_KILL, args=(0, 18, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_KILL, args=(0 | (1 << 32), SIGSTOP, 0, 0, 0, 0))
    assert killed(insns, nr=SYS_KILL, args=(0, SIGSTOP | (1 << 32), 0, 0, 0, 0))


def test_extra_fd_and_denied_syscall_families():
    insns = build()
    for nr in (2, 3, 4, 16, 21, 32, 41, 42, 56, 57, 59, 72, 101, 105, 106, 137, 157, 165, 186, 200, 213, 233, 257, 318, 435, 439):
        assert killed(insns, nr=nr, args=(3, 0x1000, 1, 0, 0, 0))
    assert killed(insns, nr=SYS_READ, args=(3, 0x1000, 1, 0, 0, 0), arch=0xC000003E ^ 1)


def test_evaluator_executes_bytes_not_a_predicate():
    insns = build()
    raw = sock_filter_bytes(insns)
    # A hand-reversed program: allow anything, then kill
    naive = sock_filter_bytes((
        (BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW),
    ))
    assert evaluate_classic_bpf_v2(naive, seccomp_data_bytes(nr=SYS_READ, args=(9, 0x1000, 1, 0, 0, 0))) == SECCOMP_RET_ALLOW
    # flip one opcode byte in the real program to an illegal opcode and the VM refuses
    corrupted = bytearray(raw)
    corrupted[0] = 0x01  # BPF_LDX|BPF_W|BPF_IMM, not in the closed opcode set used here
    with pytest.raises(ValueError):
        evaluate_classic_bpf_v2(bytes(corrupted), seccomp_data_bytes(nr=SYS_READ))
    # a truncated image is refused
    with pytest.raises(ValueError):
        evaluate_classic_bpf_v2(raw[:-1], seccomp_data_bytes(nr=SYS_READ))
    # evaluator never needs the builder's policy helpers
    assert evaluate_classic_bpf_v2(raw, seccomp_data_bytes(nr=SYS_READ, args=(3, 0x1000, 1, 0, 0, 0))) == SECCOMP_RET_ALLOW
    assert evaluate_classic_bpf_v2(raw, seccomp_data_bytes(nr=SYS_READ, args=(3, 0x1000, 1, 0, 0, 0), arch=3)) == SECCOMP_RET_KILL_PROCESS


def test_program_hash_is_stable_and_builder_refuses_widened_parameters():
    insns = build(installed_as=4096, archive_limit=1)
    h1 = classic_bpf_program_sha256(insns)
    h2 = classic_bpf_program_sha256(build(installed_as=4096, archive_limit=1))
    assert h1 == h2 and len(h1) == 64
    with pytest.raises(ValueError):
        build_classic_bpf_v2(installed_as=0, archive_limit_bytes=1)
    with pytest.raises(ValueError):
        build_classic_bpf_v2(installed_as=4096, archive_limit_bytes=1073741825)
    with pytest.raises(ValueError):
        build_classic_bpf_v2(installed_as=True, archive_limit_bytes=1)
    with pytest.raises(ValueError):
        sock_filter_bytes(((BPF_RET_K, 0, 0, 1), (0x01, 0, 0, 0)))


def test_glibc_tunables_constant_keeps_unsigned_max_trim_threshold():
    from oracle_brain.operating_model.recovery_contracts_v1 import RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
    assert 'trim_threshold=18446744073709551615' in RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
    assert 'trim_threshold=0:' not in RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
    assert 'arena_max=1' in RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
    assert 'mmap_threshold=0' in RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
    assert 'top_pad=0' in RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
