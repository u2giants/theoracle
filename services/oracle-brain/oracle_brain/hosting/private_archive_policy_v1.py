"""Single pure private TAR member policy; no native operation or authority.

The retained restore receipt helpers remain transitive dependencies. Importing
this owner never imports forward_recovery or its native/bootstrap owner.
"""
import hashlib
import tarfile
from pathlib import PurePosixPath
from .restore_receipts import MAX_TOTAL,require

MAX_FILE=512*1024**2


def _read_private_archive_v1(stream,*,metadata=False,replacement_inventory=None,collect=True):
    # ONE member policy for old byte APIs and new private streaming verification.
    files={};total=0;meta={};seen_members=set();hashes={}
    expected_dirs={str(parent) for name in replacement_inventory.files for parent in PurePosixPath(name).parents if str(parent)!='.'} if replacement_inventory is not None else set()
    with tarfile.open(fileobj=stream,mode='r:' if collect else 'r|') as archive:
        for member in archive:
            name=member.name
            while name.startswith('./'):name=name[2:]
            if replacement_inventory is not None:
                require(name not in seen_members and len(seen_members)<len(replacement_inventory.files)+len(expected_dirs)+1,'replacement archive duplicate/member bound denied')
                seen_members.add(name)
            if name in ('','.'):continue
            path=PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'archive path denied')
            require(member.isdir() or member.isfile(),'archive link/device denied')
            if member.isdir():
                if replacement_inventory is not None:require(name in expected_dirs,'extra replacement archive directory denied')
                continue
            require(name not in files and len(files)<(len(replacement_inventory.files) if replacement_inventory is not None else 128) and member.size<=MAX_FILE,'archive member/count denied')
            total+=member.size;require(total<=MAX_TOTAL,'archive aggregate denied')
            if replacement_inventory is None:
                require(member.uid==10001 and member.mode in (0o600,0o644),'archive ownership/mode differs')
                require(member.mode==0o600 or name=='.custody-lock','nonprivate archive member denied')
            else:
                seal=replacement_inventory.files.get(name)
                require(seal is not None and member.uid==seal.runtime_uid and member.mode==seal.runtime_mode==0o600 and member.size==seal.size,'replacement archive custody differs')
            meta[name]={'uid':member.uid,'mode':member.mode,'consumed_at':int(member.mtime)}
            source=archive.extractfile(member)
            if collect:
                files[name]=source.read(member.size+1)
                require(len(files[name])==member.size,'archive member truncated')
                hashes[name]=hashlib.sha256(files[name]).hexdigest()
            else:
                remaining=member.size;seal_hash=hashlib.sha256()
                while remaining:
                    chunk=source.read(min(65536,remaining))
                    require(bool(chunk),'archive member truncated')
                    remaining-=len(chunk);seal_hash.update(chunk)
                require(source.read(1)==b'','archive member exceeds declared size')
                files[name]=None;hashes[name]=seal_hash.hexdigest()
    if replacement_inventory is not None:
        require(set(files)==set(replacement_inventory.files),'replacement archive population differs')
        for name in files:require(hashes[name]==replacement_inventory.files[name].sha256,'replacement archive bytes differ')
    return (files,meta) if metadata else files

