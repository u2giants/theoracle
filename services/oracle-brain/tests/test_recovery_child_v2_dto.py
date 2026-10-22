"""Closed V2 DTO tests. Three distinct objects, no child/filter/prlimit effects."""
from datetime import timedelta
import pytest
from pydantic import ValidationError
from oracle_brain.operating_model.recovery_contracts_v1 import *
from oracle_brain.operating_model.recovery_seccomp_bpf_v2 import (
    build_classic_bpf_v2, sock_filter_bytes, classic_bpf_program_sha256,
)
from test_recovery_contracts_v1 import uid, T, H, change, file as pfile


def pin(fd):
    return RecoveryInheritedBackupFileV1(fd=fd, device=1, inode=fd, uid=1000, size=10, sha256=H)


def enforcement(**kw):
    base = dict(
        kernel_build_sha256=H, kernel_mapping_policy_sha256=H, vdso_code_sha256=H,
        vsyscall='none', interpreter_build_sha256=H, glibc_build_sha256=H,
        bpf_program_sha256=H, memory_limit_bytes=67108864, required_map_headroom=16,
        glibc_tunables=RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2,
    )
    base.update(kw)
    return RecoveryArchiveEnforcementVariantV2(**base)


def request_v2(**kw):
    base = dict(
        operation_id=uid(1), descriptor_sha256=H, custody_sha256=H,
        runtime_closure_sha256=H, installation_sha256=H, enforcement_variant_sha256=H,
        archive_limit=30, memory_limit_bytes=67108864,
        original_deadline=T, original_monotonic_end=10.0,
        archive=pin(3), inventory=pin(4), manifest=pin(5),
    )
    base.update(kw)
    return RecoveryArchiveChildRequestV2(**base)


def frame_v2(**kw):
    base = dict(
        operation_id=uid(1), descriptor_sha256=H, custody_sha256=H,
        installation_sha256=H, runtime_closure_sha256=H, enforcement_variant_sha256=H,
        archive_sha256=H, inventory_sha256=H, manifest_sha256=H,
        file_count=1, sealed_population_total_bytes=1,
    )
    base.update(kw)
    return RecoveryArchiveStructuralFrameV2(**base)


def observation_v2(**kw):
    base = dict(
        operation_id=uid(1), descriptor_sha256=H, custody_sha256=H,
        installation_sha256=H, runtime_closure_sha256=H, enforcement_variant_sha256=H,
        child_frame_sha256=H,
        preexec_soft_as_bytes=67108864, preexec_hard_as_bytes=67108864,
        stopped_soft_as_bytes=67108864, stopped_hard_as_bytes=67108864,
        exit_code=0, actual_max_rss_kib=1, actual_user_seconds=0.0, actual_system_seconds=0.0,
        currentness_verified=True, exact_cleanup_verified=True, terminal_observation='observed',
    )
    base.update(kw)
    return RecoveryArchiveParentObservationV2(**base)


def test_three_objects_are_distinct_protocols_and_parsers():
    r = request_v2()
    f = frame_v2()
    o = observation_v2()
    assert r.protocol != f.protocol != o.protocol
    assert parse_recovery_archive_child_request_v2(canonical_bytes(r.model_dump(mode='json'))) == r
    assert parse_recovery_archive_structural_frame_v2(canonical_bytes(f.model_dump(mode='json'))) == f
    assert parse_recovery_archive_parent_observation_v2(canonical_bytes(o.model_dump(mode='json'))) == o
    assert not hasattr(f, 'actual_max_rss_kib') and not hasattr(f, 'exit_code')
    assert not hasattr(r, 'actual_user_seconds')


def test_enforcement_variant_pins_closed_constants_and_false_flags():
    v = enforcement()
    assert v.audit_arch == 3221225534
    assert v.bootstrap_threads == 1 and v.personality == 0
    assert v.kernel_exported_filter_bytes_verified is False
    assert v.enforcement_qualified is False
    assert v.read_implies_exec is False and v.tsync is False
    assert parse_recovery_archive_enforcement_variant_v2(canonical_bytes(v.model_dump(mode='json'))) == v
    for field, bad in [
        ('glibc_tunables', 'glibc.malloc.arena_max=1'),
        ('kernel_exported_filter_bytes_verified', True),
        ('enforcement_qualified', 1),
        ('bootstrap_threads', 2),
        ('personality', 1),
        ('read_implies_exec', 0),
        ('tsync', True),
        ('vsyscall', 'native'),
        ('audit_arch', 3221225533),
    ]:
        with pytest.raises(ValidationError):
            change(v, **{field: bad})


def test_trim_threshold_stays_unsigned_max():
    assert '18446744073709551615' in RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2
    with pytest.raises(ValidationError):
        enforcement(glibc_tunables=RECOVERY_ARCHIVE_GLIBC_TUNABLES_V2.replace(
            '18446744073709551615', '0'))


def test_request_requires_exact_fds_3_4_5_and_binds_installation():
    r = request_v2()
    assert (r.archive.fd, r.inventory.fd, r.manifest.fd) == (3, 4, 5)
    with pytest.raises(ValidationError):
        request_v2(archive=pin(0), inventory=pin(4), manifest=pin(5))
    with pytest.raises(ValidationError):
        request_v2(archive=pin(3), inventory=pin(3), manifest=pin(5))


def test_structural_frame_is_structural_only_and_binds_request():
    r = request_v2()
    f = frame_v2()
    assert f.bind_descriptive_request(r) is f
    assert f.structural_success is True
    assert f.source_authenticated is False
    assert f.serving_authorized is False and f.dispatch_authorized is False
    assert f.automatic_retry_allowed is False
    with pytest.raises(PermissionError):
        frame_v2(installation_sha256='b' * 64).bind_descriptive_request(r)
    with pytest.raises(PermissionError):
        frame_v2(archive_sha256='b' * 64).bind_descriptive_request(r)
    with pytest.raises(PermissionError):
        frame_v2(sealed_population_total_bytes=31).bind_descriptive_request(r)
    with pytest.raises(ValidationError):
        change(f, structural_success=False)
    with pytest.raises(ValidationError):
        change(f, source_authenticated=True)


def test_parent_observation_one_wait4_and_no_authority():
    o = observation_v2()
    assert o.terminal_observation in ('refused', 'UNKNOWN', 'observed')
    assert o.kernel_exported_filter_bytes_verified is False
    assert o.enforcement_qualified is False
    assert o.serving_authorized is False and o.dispatch_authorized is False
    with pytest.raises(ValidationError):
        observation_v2(exit_code=0, term_signal=9)
    with pytest.raises(ValidationError):
        observation_v2(exit_code=None, term_signal=None)
    with pytest.raises(ValidationError):
        observation_v2(exit_code=None, term_signal=None, terminal_observation='refused')
    with pytest.raises(ValidationError):
        observation_v2(preexec_soft_as_bytes=1)
    with pytest.raises(ValidationError):
        observation_v2(currentness_verified=1)
    with pytest.raises(ValidationError):
        observation_v2(source_authenticated=True)
    with pytest.raises(ValidationError):
        change(o, term_signal=0)


def test_v1_records_remain_byte_compatible():
    v1 = RecoveryArchiveChildRequestV1(
        operation_id=uid(1), descriptor_sha256=H, custody_sha256=H, runtime_closure_sha256=H,
        archive_limit=30, memory_limit_bytes=67108864, original_deadline=T,
        original_monotonic_end=10.0, archive=pin(3), inventory=pin(4), manifest=pin(5),
    )
    raw = canonical_bytes(v1.model_dump(mode='json'))
    assert parse_recovery_archive_child_request_v1(raw) == v1
    assert v1.protocol == 'oracle-recovery-archive-check-v1'
    r2 = request_v2()
    assert r2.protocol == 'oracle-recovery-archive-check-v2'


def test_enforcement_variant_binds_emitted_program_bytes():
    insns = build_classic_bpf_v2(installed_as=67108864, archive_limit_bytes=30)
    raw = sock_filter_bytes(insns)
    v = enforcement(bpf_program_sha256=classic_bpf_program_sha256(insns))
    assert v.bind_descriptive_program(raw) is v
    with pytest.raises(PermissionError):
        enforcement(bpf_program_sha256='b' * 64).bind_descriptive_program(raw)
    with pytest.raises(TypeError):
        v.bind_descriptive_program(bytearray(raw))


def test_availability_flags_stay_false_on_v2_manifest_fields():
    fields = RecoveryArchiveRuntimeManifestV2.model_fields
    assert fields['native_loader_available'].default is False
    assert fields['archive_child_available'].default is False
    assert fields['bootstrap_output_limit_bytes'].default == 65536
