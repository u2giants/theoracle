"""Invented archive bytes only: no resource, SQL, provider or recovery grant."""
import hashlib,io,tarfile
import pytest
from pydantic import ValidationError
from oracle_brain.hosting.restore_receipts import ReplacementArchiveInventoryV1,ReplacementDumpTOCV1,verify_replacement_dump_toc_v1,Backup
from oracle_brain.hosting.forward_recovery import ReplacementForwardRecoveryV1,unpack_replacement_archive_v1,unpack,validate_docker_command


def inventory(files):
 return ReplacementArchiveInventoryV1(files={n:dict(sha256=hashlib.sha256(b).hexdigest(),size=len(b),runtime_uid=10001,runtime_mode=0o600) for n,b in sorted(files.items())},total_bytes=sum(map(len,files.values())))

def tar(files,*,name=None,kind=tarfile.REGTYPE,uid=10001,mode=0o600,duplicate=False):
 stream=io.BytesIO()
 with tarfile.open(fileobj=stream,mode='w') as archive:
  for n,raw in files.items():
   item=tarfile.TarInfo(name or n);item.size=len(raw) if kind==tarfile.REGTYPE else 0;item.type=kind;item.uid=uid;item.mode=mode
   archive.addfile(item,io.BytesIO(raw) if kind==tarfile.REGTYPE else None)
   if duplicate:archive.addfile(item,io.BytesIO(raw))
 return stream.getvalue()


def test_actual_tar_bytes_are_checked_completely_without_recovery_or_serving_authority():
 files={'databases/main.dump':b'PGDMP-invented','native/unknown.wire':b'actual invented uncertain wire'};v=inventory(files)
 raw=tar(files);observed,metadata=unpack_replacement_archive_v1(raw,v)
 assert observed==files and all(m['mode']==0o600 for m in metadata.values())
 result=ReplacementForwardRecoveryV1(v).inspect_archive_v1(raw)
 assert result['file_count']==2 and result['total_bytes']==sum(map(len,files.values()))
 assert result['serving_authorized'] is result['source_authenticated'] is result['dump_restore_enabled'] is result['business_accepted'] is False
 assert len(result['quarantine_reasons'])==4
 assert not hasattr(ReplacementForwardRecoveryV1(v),'restore') and not hasattr(ReplacementForwardRecoveryV1(v),'capture')

@pytest.mark.parametrize('attack',['missing','extra','duplicate','hash','size','symlink','hardlink','device','absolute','traversal','public-mode','wrong-owner'])
def test_new_archive_rejects_incomplete_or_hostile_actual_members(attack):
 files={'originals/source.bin':b'private invented bytes'};v=inventory(files);actual=dict(files);kwargs={}
 if attack=='missing':actual={}
 elif attack=='extra':actual['native/extra.bin']=b'x'
 elif attack=='duplicate':kwargs['duplicate']=True
 elif attack=='hash':actual['originals/source.bin']=b'x'*len(actual['originals/source.bin'])
 elif attack=='size':actual['originals/source.bin']+=b'x'
 elif attack in ('symlink','hardlink','device'):kwargs['kind']={'symlink':tarfile.SYMTYPE,'hardlink':tarfile.LNKTYPE,'device':tarfile.CHRTYPE}[attack]
 elif attack=='absolute':kwargs['name']='/originals/source.bin'
 elif attack=='traversal':kwargs['name']='../originals/source.bin'
 elif attack=='public-mode':kwargs['mode']=0o644
 else:kwargs['uid']=0
 with pytest.raises((PermissionError,ValueError)):unpack_replacement_archive_v1(tar(actual,**kwargs),v)

@pytest.mark.parametrize('patch',[{'total_bytes':True},{'total_bytes':0},{'total_bytes':9},{'schema_version':True},{'extra':True}])
def test_inventory_is_strict_direct_construction_and_revalidates_nested_seals(patch):
 v=inventory({'models/a.json':b'x'})
 with pytest.raises((PermissionError,ValidationError)):ReplacementArchiveInventoryV1.model_validate(v.model_dump()|patch)
 v.files['models/a.json']=v.files['models/a.json'].model_copy(update={'size':True})
 with pytest.raises((PermissionError,ValidationError)):ReplacementForwardRecoveryV1(v)

@pytest.mark.parametrize('name',['/originals/x','originals/../x','originals//x','originals/.','foreign/x','originals/x\0','originals'])
def test_closed_member_namespace_is_not_an_arbitrary_filesystem_selector(name):
 with pytest.raises((PermissionError,ValidationError)):inventory({name:b'x'})


def test_old_unpack_policy_and_fixed_command_allowlist_are_not_widened():
 assert unpack(tar({'legacy':b'x'}))=={'legacy':b'x'}
 with pytest.raises(PermissionError):unpack(tar({'legacy':b'x'},mode=0o644))
 with pytest.raises(PermissionError):validate_docker_command(['exec','0'*64,'pg_restore','--dbname','oracle2'])
 assert Backup.model_fields['scenario'].annotation.__args__==('public-invented-forward-v2',)


def toc_case():
 raw=b'PGDMP-invented archive';listing=b'; actual-format invented pg_restore listing\n1; 1259 42 TABLE oracle2 sources oracle2_admin\n2; 0 42 TABLE DATA oracle2 sources oracle2_admin\n3; 1259 43 TABLE public checkpoints oracle2_admin\n4; 0 43 TABLE DATA public checkpoints oracle2_admin\n'
 expected=ReplacementDumpTOCV1(archive_sha256=hashlib.sha256(raw).hexdigest(),tables=('oracle2.sources','public.checkpoints'))
 return raw,listing,expected


def test_schema_and_data_toc_rows_must_both_cover_the_complete_catalog_population():
 raw,listing,v=toc_case();result=verify_replacement_dump_toc_v1(raw,listing,v)
 assert result['table_count']==2 and result['serving_authorized'] is result['source_authenticated'] is False

@pytest.mark.parametrize('attack',['hash','missing-data','missing-schema','duplicate','foreign','comment-only','truncated','nul'])
def test_toc_never_treats_hashes_comments_or_partial_tables_as_readiness(attack):
 raw,listing,v=toc_case()
 if attack=='hash':raw+=b'x'
 elif attack=='missing-data':listing=listing.replace(b'4; 0 43 TABLE DATA public checkpoints oracle2_admin\n',b'')
 elif attack=='missing-schema':listing=listing.replace(b'1; 1259 42 TABLE oracle2 sources oracle2_admin\n',b'')
 elif attack=='duplicate':listing+=b'1; 1259 42 TABLE oracle2 sources oracle2_admin\n'
 elif attack=='foreign':listing=listing.replace(b'TABLE public checkpoints',b'TABLE foreign checkpoints')
 elif attack=='comment-only':listing=b'; TABLE oracle2 sources\n'
 elif attack=='truncated':listing=listing[:-4]
 else:listing+=b'\0'
 with pytest.raises((PermissionError,UnicodeError)):verify_replacement_dump_toc_v1(raw,listing,v)


def test_unknown_or_repeated_directory_members_cannot_hide_in_new_archive():
 files={'originals/x':b'x'};v=inventory(files)
 for names in [('foreign',),('originals','originals')]:
  stream=io.BytesIO()
  with tarfile.open(fileobj=stream,mode='w') as archive:
   for name in names:
    entry=tarfile.TarInfo(name);entry.type=tarfile.DIRTYPE;archive.addfile(entry)
   entry=tarfile.TarInfo('originals/x');entry.uid=10001;entry.mode=0o600;entry.size=1;archive.addfile(entry,io.BytesIO(b'x'))
  with pytest.raises(PermissionError):unpack_replacement_archive_v1(stream.getvalue(),v)
 with pytest.raises(PermissionError):unpack_replacement_archive_v1(b'not tar',v)
 with pytest.raises(PermissionError):unpack_replacement_archive_v1(bytearray(tar(files)),v)


def test_extra_table_with_noncanonical_spacing_refuses_instead_of_hiding():
 raw,listing,v=toc_case()
 with pytest.raises(PermissionError):verify_replacement_dump_toc_v1(raw,listing+b'5; 1 9 TABLE\tforeign hidden admin\n',v)


def test_new_wire_records_use_same_canonical_owner_and_refuse_duplicate_or_omitted_fields():
 from oracle_brain.hosting.restore_receipts import parse_replacement_archive_inventory_v1,parse_replacement_dump_toc_v1
 from oracle_brain.operating_model.contracts import canonical_bytes
 v=inventory({'models/a.json':b'x'});raw=canonical_bytes(v.model_dump(mode='json'))
 assert parse_replacement_archive_inventory_v1(raw)==v
 for bad in [b' '+raw,b'{"schema_version":1,'+raw[1:],raw.replace(b'"schema_version":1',b'"schema_version":true'),raw.replace(b'"schema_version":1,',b'')]:
  with pytest.raises((ValueError,PermissionError)):parse_replacement_archive_inventory_v1(bad)
 _,_,v=toc_case();raw=canonical_bytes(v.model_dump(mode='json'));assert parse_replacement_dump_toc_v1(raw)==v
 with pytest.raises(ValueError):parse_replacement_dump_toc_v1(b'{"schema_version":1,'+raw[1:])


def test_new_complete_archive_producer_roundtrips_private_uid_without_changing_old_pack():
 from oracle_brain.hosting.forward_recovery import pack_replacement_archive_v1,pack
 files={'control/capture-census.json':b'{}','databases/00000000-0000-0000-0000-000000000001.dump':b'PGDMP-invented'}
 v=inventory(files)
 v=ReplacementArchiveInventoryV1.model_validate({**v.model_dump(),'files':{k:{**s.model_dump(),'runtime_uid':12345} for k,s in v.files.items()}})
 first=pack_replacement_archive_v1(files,v)
 assert first==pack_replacement_archive_v1(files,v)
 observed,meta=unpack_replacement_archive_v1(first,v)
 assert observed==files and {x['uid'] for x in meta.values()}=={12345}
 assert unpack(pack({'old':b'x'}))=={'old':b'x'}

@pytest.mark.parametrize('attack',['missing','extra','changed','notbytes','baduid','oversize'])
def test_archive_producer_never_changes_supplied_custody_or_silently_drops_members(attack):
 from oracle_brain.hosting.forward_recovery import pack_replacement_archive_v1
 files={'originals/one.bin':b'x'};v=inventory(files)
 if attack=='missing':files={}
 elif attack=='extra':files['originals/other.bin']=b'x'
 elif attack=='changed':files['originals/one.bin']=b'y'
 elif attack=='notbytes':files['originals/one.bin']=bytearray(b'x')
 elif attack=='baduid':v.files['originals/one.bin']=v.files['originals/one.bin'].model_copy(update={'runtime_uid':True})
 else:v.files['originals/one.bin']=v.files['originals/one.bin'].model_copy(update={'size':536870913})
 with pytest.raises((PermissionError,ValidationError)):pack_replacement_archive_v1(files,v)
