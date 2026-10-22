"""Small closed controls only: no child process, installed closure or effects."""
import pytest
from pydantic import ValidationError
from oracle_brain.operating_model.recovery_contracts_v1 import *
from test_recovery_contracts_v1 import uid,T,H,change


def request():
 def pin(fd):return RecoveryInheritedBackupFileV1(fd=fd,device=1,inode=fd,uid=1000,size=10,sha256=H)
 return RecoveryArchiveChildRequestV1(operation_id=uid(1),descriptor_sha256=H,custody_sha256=H,runtime_closure_sha256=H,archive_limit=30,memory_limit_bytes=67108864,original_deadline=T,original_monotonic_end=10.0,archive=pin(3),inventory=pin(4),manifest=pin(5))


def test_small_fixed_control_packet_does_not_construct_authority_or_new_window():
 value=request();raw=canonical_bytes(value.model_dump(mode='json'))
 assert len(raw)<65536 and parse_recovery_archive_child_request_v1(raw)==value
 assert value.original_deadline==T and value.original_monotonic_end==10.0
 for bad in [raw+b' ',b' '*65537,raw.replace(b'"archive_limit":30',b'"archive_limit":30,"archive_limit":30')]:
  with pytest.raises(ValueError):parse_recovery_archive_child_request_v1(bad)

@pytest.mark.parametrize('field,value',[('original_monotonic_end',True),('original_monotonic_end',10),('original_monotonic_end',float('nan')),('original_monotonic_end',float('inf')),('original_monotonic_end',0.0),('archive_limit',29),('archive_limit',True),('memory_limit_bytes',True),('memory_limit_bytes',0),('original_deadline',T.replace(tzinfo=None)),('custody_sha256','not-current-authority'),('runtime_closure_sha256','versions-only')])
def test_control_refuses_unbounded_coerced_or_aggregate_drift(field,value):
 with pytest.raises(ValidationError):change(request(),**{field:value})

@pytest.mark.parametrize('field,value',[('fd',0),('fd',1),('fd',2),('fd',True),('mode',True),('mode',0o644),('link_count',True),('link_count',2),('size',0),('size',True)])
def test_inherited_input_never_accepts_standard_stream_or_nonprivate_tuple(field,value):
 with pytest.raises(ValidationError):change(request().archive,**{field:value})


def test_three_fds_and_inodes_are_distinct_and_no_path_or_sql_selector_exists():
 value=request()
 for patch in [{'inventory':value.archive},{'inventory':change(value.inventory,inode=value.archive.inode)},{'path':'/arbitrary'},{'sql':'SELECT 1'},{'argv':['caller-selected']},{'provider_key':'not-accepted'}]:
  with pytest.raises(ValidationError):change(value,**patch)


def test_success_observation_can_never_claim_serve_dispatch_retry_or_custody():
 value=RecoveryArchiveChildResultV1(operation_id=uid(1),descriptor_sha256=H,custody_sha256=H,runtime_closure_sha256=H,archive_sha256=H,inventory_sha256=H,manifest_sha256=H,file_count=1,total_bytes=1,actual_memory_limit_bytes=67108864,actual_max_rss_kib=100,actual_user_seconds=0.0,actual_system_seconds=0.0)
 for field in ['source_authenticated','serving_authorized','dispatch_authorized','automatic_retry_allowed']:
  for bad in [True,0]:
   with pytest.raises(ValidationError):change(value,**{field:bad})
 for field,bad in [('actual_user_seconds',float('inf')),('actual_system_seconds',True),('actual_max_rss_kib',True),('actual_memory_limit_bytes',-1)]:
  with pytest.raises(ValidationError):change(value,**{field:bad})
