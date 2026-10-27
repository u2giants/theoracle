"""Pure source-only classic-BPF builder and independent byte evaluator.

No seccomp install, prlimit, child, filter export, or syscall experiment.
Constants are the finite root v4 candidate list with no widening. Builder
parameters come solely from installed AS/archive authority. The evaluator
executes emitted sock_filter bytes through a classic-BPF VM and never consults
a descriptive allow-predicate.

Encoding pattern so 8-bit jt/jf never overflow: failed checks use
``JEQ/.. jt=1,jf=0`` then inline ``RET_KILL``; admitted syscalls end in inline
``RET_ALLOW``; far dispatch is ``JEQ_K nr, jt=0, jf=1`` then 32-bit ``JA``.
"""
from __future__ import annotations

from .contracts import digest

AUDIT_ARCH_X86_64 = 3221225534
PAGE_SIZE = 4096
USER_POINTER_MAX = 0x00007FFFFFFFFFFF
LOWER_HALF_END = 0x0000800000000000
X32_SYSCALL_BIT = 0x40000000
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ALLOW = 0x7FFF0000

SYS_READ = 0
SYS_WRITE = 1
SYS_FSTAT = 5
SYS_LSEEK = 8
SYS_MMAP = 9
SYS_MUNMAP = 11
SYS_RT_SIGPROCMASK = 14
SYS_RT_SIGRETURN = 15
SYS_PREAD64 = 17
SYS_EXIT = 60
SYS_KILL = 62
SYS_FUTEX = 202
SYS_CLOCK_GETTIME = 228
SYS_EXIT_GROUP = 231

FUTEX_WAIT_PRIVATE = 128
FUTEX_WAKE_PRIVATE = 129
SIGSTOP = 19
EXIT_SUCCESS_STATUS = 0
EXIT_FAILURE_STATUS = 70
PROT_READ_WRITE = 3
MAP_PRIVATE_ANONYMOUS = 0x22
FD_INVAL64 = 0xFFFFFFFFFFFFFFFF
COUNT_MIN = 1
COUNT_MAX = 65536
SIGSETSIZE = 8
FUTEX_VAL_MAX = 0x7FFFFFFF
CLOCK_IDS = (0, 1)
RT_SIGPROCMASK_HOW = (0, 1, 2)
LSEEK_WHENCE = (0, 1, 2)
SEEK_SET = 0
READ_FDS = (3, 4, 5)
WRITE_FDS = (1, 2)

OFF_NR = 0
OFF_ARCH = 4
OFF_ARGS = 16

BPF_LD_W_ABS = 0x20
BPF_LD_W_MEM = 0x60
BPF_LDX_W_MEM = 0x61
BPF_ST = 0x02
BPF_ALU_ADD_K = 0x04
BPF_ALU_ADD_X = 0x0C
BPF_JMP_JA = 0x05
BPF_JMP_JEQ_K = 0x15
BPF_JMP_JGT_K = 0x25
BPF_JMP_JGT_X = 0x2D
BPF_JMP_JGE_K = 0x35
BPF_JMP_JSET_K = 0x45
BPF_RET_K = 0x06

BPF_INSN_BYTES = 8
SECCOMP_DATA_BYTES = 64
MAX_BPF_INSNS = 4096

BUILDER_IMMEDIATE_INVENTORY = frozenset({
    AUDIT_ARCH_X86_64, X32_SYSCALL_BIT, SECCOMP_RET_KILL_PROCESS, SECCOMP_RET_ALLOW,
    PAGE_SIZE, USER_POINTER_MAX, LOWER_HALF_END, FD_INVAL64, COUNT_MIN, COUNT_MAX,
    SIGSETSIZE, FUTEX_VAL_MAX, FUTEX_WAIT_PRIVATE, FUTEX_WAKE_PRIVATE, SIGSTOP,
    EXIT_SUCCESS_STATUS, EXIT_FAILURE_STATUS, PROT_READ_WRITE, MAP_PRIVATE_ANONYMOUS,
    SEEK_SET, 0x7FFF, 0xFFFFFFFF, 0x8000, 0xFFF, 0x3,
    SYS_READ, SYS_WRITE, SYS_FSTAT, SYS_LSEEK, SYS_MMAP, SYS_MUNMAP,
    SYS_RT_SIGPROCMASK, SYS_RT_SIGRETURN, SYS_PREAD64, SYS_EXIT, SYS_KILL,
    SYS_FUTEX, SYS_CLOCK_GETTIME, SYS_EXIT_GROUP,
})

BPF_ALLOWED_OPCODES = frozenset({
    BPF_LD_W_ABS, BPF_LD_W_MEM, BPF_LDX_W_MEM, BPF_ST, BPF_ALU_ADD_K, BPF_ALU_ADD_X,
    BPF_JMP_JA, BPF_JMP_JEQ_K, BPF_JMP_JGT_K, BPF_JMP_JGT_X, BPF_JMP_JGE_K,
    BPF_JMP_JSET_K, BPF_RET_K,
})


def sock_filter_bytes(insns) -> bytes:
    if type(insns) not in (list, tuple) or not insns or len(insns) > MAX_BPF_INSNS:
        raise ValueError('finite nonempty classic-BPF program required')
    out = bytearray()
    for insn in insns:
        if type(insn) is not tuple or len(insn) != 4:
            raise ValueError('exact classic-BPF instruction tuple required')
        code, jt, jf, k = insn
        if type(code) is not int or code not in BPF_ALLOWED_OPCODES:
            raise ValueError('closed classic-BPF opcode inventory required')
        if type(jt) is not int or type(jf) is not int or not 0 <= jt <= 255 or not 0 <= jf <= 255:
            raise ValueError('exact classic-BPF jump offset required')
        if type(k) is not int or not 0 <= k <= 0xFFFFFFFF:
            raise ValueError('exact classic-BPF immediate required')
        out += int(code).to_bytes(2, 'little') + bytes((jt, jf)) + int(k).to_bytes(4, 'little')
    return bytes(out)


def classic_bpf_program_sha256(insns) -> str:
    import hashlib
    return hashlib.sha256(sock_filter_bytes(insns)).hexdigest()


class _Asm:
    def __init__(self):
        self.insns = []
        self.labels = {}
        self.refs = []

    def label(self, name):
        if name in self.labels:
            raise ValueError('duplicate classic-BPF label required to be unique')
        self.labels[name] = len(self.insns)

    def emit(self, code, jt=0, jf=0, k=0):
        self.insns.append([int(code), int(jt), int(jf), int(k) & 0xFFFFFFFF])
        return len(self.insns) - 1

    def ld(self, off):
        return self.emit(BPF_LD_W_ABS, k=off)

    def ld_mem(self, slot):
        return self.emit(BPF_LD_W_MEM, k=slot)

    def st(self, slot):
        return self.emit(BPF_ST, k=slot)

    def ldx(self, slot):
        return self.emit(BPF_LDX_W_MEM, k=slot)

    def add_x(self):
        return self.emit(BPF_ALU_ADD_X)

    def add_k(self, k):
        return self.emit(BPF_ALU_ADD_K, k=k)

    def ret_allow(self):
        return self.emit(BPF_RET_K, k=SECCOMP_RET_ALLOW)

    def ret_kill(self):
        return self.emit(BPF_RET_K, k=SECCOMP_RET_KILL_PROCESS)

    def ja(self, target):
        self.refs.append((self.emit(BPF_JMP_JA), 'k', target))

    def jeq(self, k, true_label, false_label):
        idx = self.emit(BPF_JMP_JEQ_K, k=k)
        self.refs.append((idx, 'jt', true_label))
        self.refs.append((idx, 'jf', false_label))

    def jgt(self, k, true_label, false_label):
        idx = self.emit(BPF_JMP_JGT_K, k=k)
        self.refs.append((idx, 'jt', true_label))
        self.refs.append((idx, 'jf', false_label))

    def jge(self, k, true_label, false_label):
        idx = self.emit(BPF_JMP_JGE_K, k=k)
        self.refs.append((idx, 'jt', true_label))
        self.refs.append((idx, 'jf', false_label))

    def jset(self, k, true_label, false_label):
        idx = self.emit(BPF_JMP_JSET_K, k=k)
        self.refs.append((idx, 'jt', true_label))
        self.refs.append((idx, 'jf', false_label))

    def jgt_x(self, true_label, false_label):
        idx = self.emit(BPF_JMP_JGT_X)
        self.refs.append((idx, 'jt', true_label))
        self.refs.append((idx, 'jf', false_label))

    def finish(self):
        for idx, kind, label in self.refs:
            target = self.labels[label]
            rel = target - (idx + 1)
            if kind == 'k':
                if not 0 <= rel <= 0xFFFFFFFF:
                    raise ValueError('classic-BPF JA offset required')
                self.insns[idx][3] = rel
            else:
                if not 0 <= rel <= 255:
                    raise ValueError(f'classic-BPF short jump exceeds 8-bit field at {idx} -> {label} ({rel})')
                self.insns[idx][1 if kind == 'jt' else 2] = rel
        return tuple((c, jt, jf, k) for c, jt, jf, k in self.insns)


def _arg_off(i, word):
    return OFF_ARGS + 8 * i + 4 * word


def _u64_eq(asm, arg_i, value, ok, tag):
    hi, lo = (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
    asm.ld(_arg_off(arg_i, 1))
    asm.jeq(hi, f'{tag}_h', f'{tag}_k1')
    asm.label(f'{tag}_h')
    asm.ld(_arg_off(arg_i, 0))
    asm.jeq(lo, ok, f'{tag}_k1')
    asm.label(f'{tag}_k1')
    asm.ret_kill()


def _u64_zero(asm, arg_i, ok, tag):
    asm.ld(_arg_off(arg_i, 1))
    asm.jeq(0, f'{tag}_h', f'{tag}_k1')
    asm.label(f'{tag}_h')
    asm.ld(_arg_off(arg_i, 0))
    asm.jeq(0, ok, f'{tag}_k1')
    asm.label(f'{tag}_k1')
    asm.ret_kill()


def _u64_range(asm, arg_i, lo_b, hi_b, ok, tag):
    hi_hi, hi_lo = hi_b >> 32, hi_b & 0xFFFFFFFF
    lo_hi, lo_lo = lo_b >> 32, lo_b & 0xFFFFFFFF
    asm.ld(_arg_off(arg_i, 1))
    asm.jgt(hi_hi, f'{tag}_k', f'{tag}_hle')
    asm.label(f'{tag}_hle')
    asm.jeq(hi_hi, f'{tag}_heq', f'{tag}_min')
    asm.label(f'{tag}_heq')
    asm.ld(_arg_off(arg_i, 0))
    asm.jgt(hi_lo, f'{tag}_k', f'{tag}_min')
    asm.label(f'{tag}_min')
    asm.ld(_arg_off(arg_i, 1))
    asm.jgt(lo_hi, ok, f'{tag}_hmin')
    asm.label(f'{tag}_hmin')
    asm.jeq(lo_hi, f'{tag}_lchk', f'{tag}_k')
    asm.label(f'{tag}_lchk')
    asm.ld(_arg_off(arg_i, 0))
    asm.jge(lo_lo, ok, f'{tag}_k')
    asm.label(f'{tag}_k')
    asm.ret_kill()


def _nonnull(asm, arg_i, ok, tag):
    asm.ld(_arg_off(arg_i, 1))
    asm.jgt(0x7FFF, f'{tag}_k', f'{tag}_h')
    asm.label(f'{tag}_h')
    asm.jeq(0, f'{tag}_hz', ok)
    asm.label(f'{tag}_hz')
    asm.ld(_arg_off(arg_i, 0))
    asm.jeq(0, f'{tag}_k', ok)
    asm.label(f'{tag}_k')
    asm.ret_kill()


def _nullable(asm, arg_i, ok, tag):
    asm.ld(_arg_off(arg_i, 1))
    asm.jgt(0x7FFF, f'{tag}_k', ok)
    asm.label(f'{tag}_k')
    asm.ret_kill()


def _fd_in(asm, arg_i, fds, ok, tag):
    asm.ld(_arg_off(arg_i, 1))
    asm.jeq(0, f'{tag}_h', f'{tag}_k')
    asm.label(f'{tag}_h')
    asm.ld(_arg_off(arg_i, 0))
    for i, fd in enumerate(fds):
        more = i + 1 < len(fds)
        asm.jeq(fd, ok, f'{tag}_{i}' if more else f'{tag}_k')
        if more:
            asm.label(f'{tag}_{i}')
    asm.label(f'{tag}_k')
    asm.ret_kill()


def _count(asm, arg_i, ok, tag):
    _u64_range(asm, arg_i, COUNT_MIN, COUNT_MAX, ok, tag)


def _munmap_bound(asm, ok):
    # sum = addr+length in full 64-bit; allow only sum <= 0x0000800000000000
    asm.ld(_arg_off(0, 0))
    asm.st(0)                    # M[0] = al
    asm.ld(_arg_off(1, 0))
    asm.st(1)                    # M[1] = ll
    asm.ldx(1)                   # X = ll
    asm.ld_mem(0)                # A = al
    asm.add_x()                  # A = sum_lo
    asm.st(1)                    # M[1] = sum_lo
    asm.ldx(1)                   # X = sum_lo
    asm.ld_mem(0)                # A = al
    asm.jgt_x('mu_cy', 'mu_nc')  # carry when al > sum_lo
    asm.label('mu_cy')
    asm.ld(_arg_off(0, 1))
    asm.st(2)
    asm.ld(_arg_off(1, 1))
    asm.ldx(2)
    asm.add_x()
    asm.add_k(1)
    asm.ja('mu_hi')
    asm.label('mu_nc')
    asm.ld(_arg_off(0, 1))
    asm.st(2)
    asm.ld(_arg_off(1, 1))
    asm.ldx(2)
    asm.add_x()
    asm.label('mu_hi')
    asm.jgt(0x8000, 'mu_bk', 'mu_le')
    asm.label('mu_le')
    asm.jeq(0x8000, 'mu_eq', ok)
    asm.label('mu_eq')
    asm.ld_mem(1)
    asm.jeq(0, ok, 'mu_bk')
    asm.label('mu_bk')
    asm.ret_kill()


def build_classic_bpf_v2(*, installed_as, archive_limit_bytes):
    """Exact architecture-checked classic-BPF program (root v4 only)."""
    if type(installed_as) is not int or not 1 <= installed_as <= 9223372036854775807:
        raise ValueError('exact installed AS ceiling required')
    if type(archive_limit_bytes) is not int or not 1 <= archive_limit_bytes <= 1073741824:
        raise ValueError('exact installed archive ceiling required')
    asm = _Asm()
    asm.ld(OFF_ARCH)
    asm.jeq(AUDIT_ARCH_X86_64, 'arch_ok', 'arch_bad')
    asm.label('arch_bad')
    asm.ret_kill()
    asm.label('arch_ok')
    asm.ld(OFF_NR)
    asm.jset(X32_SYSCALL_BIT, 'x32_bad', 'not_x32')
    asm.label('x32_bad')
    asm.ret_kill()
    asm.label('not_x32')
    for nr, lab in (
        (SYS_READ, 's_read'), (SYS_WRITE, 's_write'), (SYS_FSTAT, 's_fstat'),
        (SYS_LSEEK, 's_lseek'), (SYS_MMAP, 's_mmap'), (SYS_MUNMAP, 's_munmap'),
        (SYS_RT_SIGPROCMASK, 's_rsp'), (SYS_RT_SIGRETURN, 's_rtr'),
        (SYS_PREAD64, 's_pread'), (SYS_EXIT, 's_exit'), (SYS_KILL, 's_kill'),
        (SYS_FUTEX, 's_futex'), (SYS_CLOCK_GETTIME, 's_cgt'),
        (SYS_EXIT_GROUP, 's_eg'),
    ):
        asm.emit(BPF_JMP_JEQ_K, jt=0, jf=1, k=nr)
        asm.ja(lab)
    asm.ret_kill()

    asm.label('s_read')
    _fd_in(asm, 0, READ_FDS, 'rd1', 'rdf')
    asm.label('rd1')
    _nonnull(asm, 1, 'rd2', 'rdp')
    asm.label('rd2')
    _count(asm, 2, 'rd_ok', 'rdc')
    asm.label('rd_ok')
    asm.ret_allow()

    asm.label('s_write')
    _fd_in(asm, 0, WRITE_FDS, 'wr1', 'wrf')
    asm.label('wr1')
    _nonnull(asm, 1, 'wr2', 'wrp')
    asm.label('wr2')
    _count(asm, 2, 'wr_ok', 'wrc')
    asm.label('wr_ok')
    asm.ret_allow()

    asm.label('s_fstat')
    _fd_in(asm, 0, READ_FDS, 'fs1', 'fsf')
    asm.label('fs1')
    _nonnull(asm, 1, 'fs_ok', 'fsp')
    asm.label('fs_ok')
    asm.ret_allow()

    asm.label('s_lseek')
    _fd_in(asm, 0, READ_FDS, 'ls1', 'lsf')
    asm.label('ls1')
    asm.ld(_arg_off(2, 1))
    asm.jeq(0, 'ls_wh', 'ls_k')
    asm.label('ls_wh')
    asm.ld(_arg_off(2, 0))
    asm.jeq(SEEK_SET, 'ls_set', 'ls_w1')
    asm.label('ls_w1')
    asm.jeq(1, 'ls_cur', 'ls_w2')
    asm.label('ls_w2')
    asm.jeq(2, 'ls_cur', 'ls_k')
    asm.label('ls_set')
    _u64_range(asm, 1, 0, archive_limit_bytes, 'ls_ok', 'lss')
    asm.label('ls_cur')
    asm.ld(_arg_off(1, 1))
    asm.jeq(0, 'ls_pos', 'ls_nh')
    asm.label('ls_pos')
    asm.ld(_arg_off(1, 0))
    asm.jgt(archive_limit_bytes, 'ls_k', 'ls_ok')
    asm.label('ls_nh')
    asm.jeq(0xFFFFFFFF, 'ls_neg', 'ls_k')
    asm.label('ls_neg')
    asm.ld(_arg_off(1, 0))
    asm.jge((0x100000000 - archive_limit_bytes) & 0xFFFFFFFF, 'ls_ok', 'ls_k')
    asm.label('ls_ok')
    asm.ret_allow()
    asm.label('ls_k')
    asm.ret_kill()

    asm.label('s_mmap')
    _u64_zero(asm, 0, 'mm1', 'mma')
    asm.label('mm1')
    _u64_range(asm, 1, 1, installed_as, 'mm2', 'mml')
    asm.label('mm2')
    _u64_eq(asm, 2, PROT_READ_WRITE, 'mm3', 'mmp')
    asm.label('mm3')
    _u64_eq(asm, 3, MAP_PRIVATE_ANONYMOUS, 'mm4', 'mmf')
    asm.label('mm4')
    _u64_eq(asm, 4, FD_INVAL64, 'mm5', 'mmd')
    asm.label('mm5')
    _u64_zero(asm, 5, 'mm_ok', 'mmo')
    asm.label('mm_ok')
    asm.ret_allow()

    asm.label('s_munmap')
    _nonnull(asm, 0, 'mu1', 'mup')
    asm.label('mu1')
    asm.ld(_arg_off(0, 0))
    asm.jset(PAGE_SIZE - 1, 'mu_k', 'mu2')
    asm.label('mu2')
    _u64_range(asm, 1, 1, installed_as, 'mu3', 'mul')
    asm.label('mu3')
    asm.ld(_arg_off(1, 0))
    asm.jset(PAGE_SIZE - 1, 'mu_k', 'mu4')
    asm.label('mu4')
    _munmap_bound(asm, 'mu_ok')
    asm.label('mu_ok')
    asm.ret_allow()
    asm.label('mu_k')
    asm.ret_kill()

    asm.label('s_rsp')
    asm.ld(_arg_off(0, 1))
    asm.jeq(0, 'rsph', 'rspk')
    asm.label('rsph')
    asm.ld(_arg_off(0, 0))
    asm.jeq(0, 'rsp1', 'rsh1')
    asm.label('rsh1')
    asm.jeq(1, 'rsp1', 'rsh2')
    asm.label('rsh2')
    asm.jeq(2, 'rsp1', 'rspk')
    asm.label('rsp1')
    _nullable(asm, 1, 'rsp2', 'rsps')
    asm.label('rsp2')
    _nullable(asm, 2, 'rsp3', 'rspo')
    asm.label('rsp3')
    _u64_eq(asm, 3, SIGSETSIZE, 'rsp_ok', 'rspz')
    asm.label('rsp_ok')
    asm.ret_allow()
    asm.label('rspk')
    asm.ret_kill()

    asm.label('s_rtr')
    asm.ret_allow()

    asm.label('s_pread')
    _fd_in(asm, 0, READ_FDS, 'pr1', 'prf')
    asm.label('pr1')
    _nonnull(asm, 1, 'pr2', 'prp')
    asm.label('pr2')
    _count(asm, 2, 'pr3', 'prc')
    asm.label('pr3')
    _u64_range(asm, 3, 0, archive_limit_bytes, 'pr_ok', 'pro')
    asm.label('pr_ok')
    asm.ret_allow()

    asm.label('s_exit')
    asm.ld(_arg_off(0, 1))
    asm.jeq(0, 'exh', 'exk')
    asm.label('exh')
    asm.ld(_arg_off(0, 0))
    asm.jeq(EXIT_SUCCESS_STATUS, 'ex_ok', 'exf')
    asm.label('exf')
    asm.jeq(EXIT_FAILURE_STATUS, 'ex_ok', 'exk')
    asm.label('ex_ok')
    asm.ret_allow()
    asm.label('exk')
    asm.ret_kill()

    asm.label('s_kill')
    _u64_zero(asm, 0, 'kl1', 'klz')
    asm.label('kl1')
    _u64_eq(asm, 1, SIGSTOP, 'kl_ok', 'kls')
    asm.label('kl_ok')
    asm.ret_allow()

    asm.label('s_futex')
    _nonnull(asm, 0, 'fx1', 'fxp')
    asm.label('fx1')
    asm.ld(_arg_off(0, 0))
    asm.jset(0x3, 'fxk', 'fx2')
    asm.label('fx2')
    asm.ld(_arg_off(1, 1))
    asm.jeq(0, 'fx3', 'fxk')
    asm.label('fx3')
    asm.ld(_arg_off(1, 0))
    asm.jeq(FUTEX_WAIT_PRIVATE, 'fxw', 'fxb')
    asm.label('fxb')
    asm.jeq(FUTEX_WAKE_PRIVATE, 'fxv', 'fxk')
    asm.label('fxw')
    _u64_zero(asm, 3, 'fx4', 'fxt')
    asm.label('fx4')
    _u64_zero(asm, 4, 'fx5', 'fxu')
    asm.label('fx5')
    _u64_zero(asm, 5, 'fxv', 'fx3')
    asm.label('fxv')
    asm.ld(_arg_off(2, 1))
    asm.jeq(0, 'fx6', 'fxk')
    asm.label('fx6')
    asm.ld(_arg_off(2, 0))
    asm.jgt(FUTEX_VAL_MAX, 'fxk', 'fx_ok')
    asm.label('fx_ok')
    asm.ret_allow()
    asm.label('fxk')
    asm.ret_kill()

    asm.label('s_cgt')
    asm.ld(_arg_off(0, 1))
    asm.jeq(0, 'cgh', 'cgk')
    asm.label('cgh')
    asm.ld(_arg_off(0, 0))
    asm.jeq(0, 'cg1', 'cgb')
    asm.label('cgb')
    asm.jeq(1, 'cg1', 'cgk')
    asm.label('cg1')
    _nonnull(asm, 1, 'cg_ok', 'cgp')
    asm.label('cg_ok')
    asm.ret_allow()
    asm.label('cgk')
    asm.ret_kill()

    asm.label('s_eg')
    asm.ld(_arg_off(0, 1))
    asm.jeq(0, 'egh', 'egk')
    asm.label('egh')
    asm.ld(_arg_off(0, 0))
    asm.jeq(EXIT_SUCCESS_STATUS, 'eg_ok', 'egf')
    asm.label('egf')
    asm.jeq(EXIT_FAILURE_STATUS, 'eg_ok', 'egk')
    asm.label('eg_ok')
    asm.ret_allow()
    asm.label('egk')
    asm.ret_kill()

    return asm.finish()


def evaluate_classic_bpf_v2(program_bytes, seccomp_data):
    """Independently execute classic-BPF bytes against a seccomp_data image.

    Classic-BPF VM only: decodes sock_filter instructions and steps them.
    Never imports, calls, or compares against any descriptive allow-predicate.
    """
    if type(program_bytes) is not bytes or len(program_bytes) == 0 or len(program_bytes) % BPF_INSN_BYTES:
        raise ValueError('exact sock_filter byte image required')
    if type(seccomp_data) is not bytes or len(seccomp_data) != SECCOMP_DATA_BYTES:
        raise ValueError('exact 64-byte seccomp_data image required')
    ninsns = len(program_bytes) // BPF_INSN_BYTES
    if ninsns > MAX_BPF_INSNS:
        raise ValueError('finite classic-BPF program required')
    mem = [0] * 16
    a = x = pc = steps = 0
    limit = MAX_BPF_INSNS * 8
    while True:
        steps += 1
        if steps > limit:
            raise ValueError('classic-BPF evaluation exceeded finite step budget')
        if pc < 0 or pc >= ninsns:
            raise ValueError('classic-BPF pc left the program')
        base = pc * BPF_INSN_BYTES
        code = int.from_bytes(program_bytes[base:base + 2], 'little')
        jt = program_bytes[base + 2]
        jf = program_bytes[base + 3]
        k = int.from_bytes(program_bytes[base + 4:base + 8], 'little')
        pc += 1
        if code == BPF_LD_W_ABS:
            if k % 4 or k + 4 > SECCOMP_DATA_BYTES:
                raise ValueError('classic-BPF absolute load outside seccomp_data')
            a = int.from_bytes(seccomp_data[k:k + 4], 'little')
        elif code == BPF_LD_W_MEM:
            if k >= 16:
                raise ValueError('classic-BPF scratch slot required')
            a = mem[k]
        elif code == BPF_LDX_W_MEM:
            if k >= 16:
                raise ValueError('classic-BPF scratch slot required')
            x = mem[k]
        elif code == BPF_ST:
            if k >= 16:
                raise ValueError('classic-BPF scratch slot required')
            mem[k] = a & 0xFFFFFFFF
        elif code == BPF_ALU_ADD_X:
            a = (a + x) & 0xFFFFFFFF
        elif code == BPF_ALU_ADD_K:
            a = (a + k) & 0xFFFFFFFF
        elif code == BPF_JMP_JA:
            pc = pc + k
        elif code == BPF_JMP_JEQ_K:
            pc += jt if a == k else jf
        elif code == BPF_JMP_JGT_K:
            pc += jt if a > k else jf
        elif code == BPF_JMP_JGT_X:
            pc += jt if a > x else jf
        elif code == BPF_JMP_JGE_K:
            pc += jt if a >= k else jf
        elif code == BPF_JMP_JSET_K:
            pc += jt if (a & k) else jf
        elif code == BPF_RET_K:
            return k & 0xFFFFFFFF
        else:
            raise ValueError('closed classic-BPF opcode inventory required')
        if pc < 0 or pc > ninsns:
            raise ValueError('classic-BPF pc left the program')


def seccomp_data_bytes(*, nr, arch=AUDIT_ARCH_X86_64, instruction_pointer=0, args=(0, 0, 0, 0, 0, 0)):
    if type(args) not in (list, tuple) or len(args) != 6:
        raise ValueError('exact six seccomp arguments required')
    words = [int(nr) & 0xFFFFFFFF, int(arch) & 0xFFFFFFFF]
    words.append(int(instruction_pointer) & 0xFFFFFFFF)
    words.append((int(instruction_pointer) >> 32) & 0xFFFFFFFF)
    for value in args:
        value = int(value) & 0xFFFFFFFFFFFFFFFF
        words.append(value & 0xFFFFFFFF)
        words.append((value >> 32) & 0xFFFFFFFF)
    out = b''.join(w.to_bytes(4, 'little') for w in words)
    if len(out) != SECCOMP_DATA_BYTES:
        raise ValueError('exact seccomp_data image required')
    return out
