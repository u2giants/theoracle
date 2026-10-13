"""Invented archive bytes and NONAUTHORIZING resolver fixtures only."""
import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest import mock
import tempfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('packets',Path(__file__).with_name('analytical_source_packets.py'))
p=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=p;spec.loader.exec_module(p)
FOLDER=ROOT/'dev/oracle2/analytics'

class InventedAuthority(p.CurrentProductDeliveryAuthority):
    """Pure local test dependency; never installed or an actual issuer."""
    def __init__(self,grant):self.grant=grant;self.calls=0
    def current(self,principal,binding):self.calls+=1;return self.grant

class Packets(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.sources=self.root/'sources';self.cache=self.root/'cache';self.sources.mkdir(mode=0o700);self.cache.mkdir(mode=0o700)
        self.bytes=b'INVENTED PUBLIC ARCHIVE ONLY\x00\xff'*40000
        self.manifest=json.loads((FOLDER/'source-manifest.json').read_bytes());artifact=next(a for a in self.manifest['artifacts'] if a['id']=='pm4py');artifact.update(bytes=len(self.bytes),sha256=p.sha(self.bytes))
        self.filename=self.sources/artifact['filename'];self.filename.write_bytes(self.bytes);self.filename.chmod(0o600)
        self.raw=json.dumps(self.manifest,separators=(',',':')).encode();self.binding=p.ProductBinding(p.sha(self.raw),'a'*40,'sha256:'+'b'*64)
        self.grant=p.DeliveryGrant(self.binding,'invented-viewer','permissions-v1','independent-custodian','independent-reviewer','c'*64,'d'*64,'e'*64,200,frozenset({'source_delivery'}))
        self.authority=InventedAuthority(self.grant)
    def tearDown(self):self.tmp.cleanup()
    def store(self,authority=None,raw=None,binding=None):
        return p.SourcePacketStore(raw or self.raw,(FOLDER/'requirements.lock').read_bytes(),(FOLDER/'Dockerfile').read_bytes(),(FOLDER/'Dockerfile.dockerignore').read_bytes(),binding or self.binding,self.sources,self.cache,authority=authority,clock=lambda:100)
    def request(self,index=0):
        return p.ChunkRequest(self.binding,'invented-viewer','pm4py',index,index*p.validator.CHUNK,min((index+1)*p.validator.CHUNK,len(self.bytes)))
    def test_default_resolver_denies_before_source_or_cache_open(self):
        store=self.store()
        with mock.patch.object(os,'open',side_effect=AssertionError('archive/cache opened before permission')):
            with self.assertRaisesRegex(ValueError,'resolver unavailable'):store.serve(self.request())
    def test_exact_chunk_reconstruction_and_one_full_original_read(self):
        store=self.store(self.authority);original=os.open;opens=[]
        def opened(path,*args,**kwargs):
            if str(path)==self.filename.name:opens.append(str(path))
            return original(path,*args,**kwargs)
        with mock.patch.object(os,'open',side_effect=opened):
            chunks=[store.serve(self.request(i)) for i in range((len(self.bytes)+p.validator.CHUNK-1)//p.validator.CHUNK)]
            store.serve(self.request(0))
        self.assertEqual(opens,[self.filename.name]);self.assertEqual(b''.join(c['payload'] for c in chunks),self.bytes)
        proof=p.reconstruction_proof(self.binding,'pm4py',p.sha(self.bytes),len(self.bytes),chunks)
        self.assertFalse(proof['product_admission']);self.assertFalse(proof['delivery_decision_issued'])
        self.assertEqual(next(self.cache.glob('*.archive')).stat().st_mode&0o777,0o400)
        self.assertEqual(len(store.artifacts),37)
    def test_wrong_manifest_revision_image_and_boolean_resolver_cannot_admit(self):
        for bad in (replace(self.binding,manifest_sha256='f'*64),replace(self.binding,source_revision=True),replace(self.binding,image_digest='mutable:latest')):
            with self.assertRaises(ValueError):self.store(binding=bad)
        for bad in (True,'a'*64,lambda *a:self.grant):
            with self.assertRaises(ValueError):self.store(authority=bad)
        store=self.store(self.authority)
        for bad in (replace(self.binding,source_revision='f'*40),replace(self.binding,image_digest='sha256:'+'f'*64),replace(self.binding,manifest_sha256='f'*64)):
            with mock.patch.object(os,'open',side_effect=AssertionError('wrong product opened bytes')):
                with self.assertRaises(ValueError):store.serve(replace(self.request(),binding=bad))
    def test_missing_notice_and_changed_rights_refuse_without_bytes(self):
        for damage in ('notice','rights','binary'):
            value=copy.deepcopy(self.manifest)
            if damage=='notice':value['artifacts'][0]['notices']={}
            elif damage=='rights':value['rights']['delivery']=True
            else:next(a for a in value['artifacts'] if a['id']=='pulp')['binary_inventory'].pop()
            raw=json.dumps(value).encode()
            with self.assertRaises(ValueError):self.store(raw=raw,binding=replace(self.binding,manifest_sha256=p.sha(raw)))
    def test_actual_wrong_hash_size_symlink_and_cache_mutation_refuse(self):
        for damage in ('hash','size','symlink'):
            store=self.store(self.authority)
            self.filename.unlink(missing_ok=True)
            if damage=='symlink':self.filename.symlink_to(self.root/'absent')
            else:self.filename.write_bytes((b'x'*len(self.bytes)) if damage=='hash' else b'x');self.filename.chmod(0o600)
            with self.assertRaises((ValueError,OSError)):store.serve(self.request())
            self.assertFalse(list(self.cache.glob('*.archive')))
        self.filename.unlink();self.filename.write_bytes(self.bytes);self.filename.chmod(0o600)
        store=self.store(self.authority);store.serve(self.request());cached=next(self.cache.glob('*.archive'));cached.chmod(0o600)
        with self.assertRaises(ValueError):store.serve(self.request())
    def test_invalid_chunk_range_cross_artifact_and_reordered_reconstruction(self):
        store=self.store(self.authority)
        for request in (replace(self.request(),artifact_id='../pm4py'),replace(self.request(),chunk_index=True),replace(self.request(),end=len(self.bytes)+1),replace(self.request(),start=-1),replace(self.request(),chunk_index=999)):
            with mock.patch.object(os,'open',side_effect=AssertionError('invalid chunk opened bytes')):
                with self.assertRaises(ValueError):store.serve(request)
        chunks=[store.serve(self.request(i)) for i in range(2)]
        for bad in ([{**chunks[0],'artifact_id':'pulp'},chunks[1]],list(reversed(chunks)),chunks[:1],[{**chunks[0],'payload':b'changed'},chunks[1]]):
            with self.assertRaises(ValueError):p.reconstruction_proof(self.binding,'pm4py',p.sha(self.bytes),len(self.bytes),bad)
    def test_current_permission_revocation_expiry_and_independence(self):
        store=self.store(self.authority);store.serve(self.request())
        for grant in (None,True,replace(self.grant,expires_at=100),replace(self.grant,rights=frozenset({'build'})),replace(self.grant,issuer='invented-viewer'),replace(self.grant,binding=replace(self.binding,source_revision='f'*40))):
            self.authority.grant=grant
            with mock.patch.object(os,'open',side_effect=AssertionError('revoked permission opened bytes')):
                with self.assertRaises(ValueError):store.serve(self.request())
    def test_revocation_during_verification_publishes_no_cache(self):
        class Revoked(InventedAuthority):
            def current(inner,*args):
                inner.calls+=1;return inner.grant if inner.calls<4 else None
        store=self.store(Revoked(self.grant))
        with self.assertRaises(ValueError):store.serve(self.request())
        self.assertFalse(list(self.cache.iterdir()))
    def test_per_artifact_and_chunk_limits_cannot_be_widened(self):
        for damage in ('artifact','chunk'):
            value=copy.deepcopy(self.manifest)
            if damage=='artifact':next(a for a in value['artifacts'] if a['id']=='pm4py')['bytes']=p.validator.LIMIT+1
            else:value['chunk_limit_bytes']=p.validator.CHUNK+1
            raw=json.dumps(value).encode()
            with self.assertRaises(ValueError):self.store(raw=raw,binding=replace(self.binding,manifest_sha256=p.sha(raw)))
    def test_symlinked_source_root_and_existing_cache_are_not_reused(self):
        link=self.root/'linked';link.symlink_to(self.sources,target_is_directory=True)
        store=self.store(self.authority);store.source_root=link
        with self.assertRaises(OSError):store.serve(self.request())
        store=self.store(self.authority);collision=self.cache/(p.sha(self.bytes)+'.archive');collision.write_bytes(b'foreign');collision.chmod(0o400)
        with self.assertRaises(FileExistsError):store.serve(self.request())
        self.assertEqual(collision.read_bytes(),b'foreign')
    def test_changed_permission_revision_during_cached_read_denies_response(self):
        store=self.store(self.authority);store.serve(self.request())
        class Changed(InventedAuthority):
            def current(inner,*args):
                inner.calls+=1
                return inner.grant if inner.calls<3 else replace(inner.grant,permissions_revision='changed')
        store.authority=Changed(self.grant)
        with self.assertRaises(ValueError):store.serve(self.request())

    def test_cache_parent_swap_stays_on_held_inode_no_foreign_bytes_opened(self):
        store=self.store(self.authority);original_open=os.open;original_link=os.link
        held_cache=self.root/'retained-cache';foreign_payload=b'FOREIGN-NOT-OPENED';opened=[];links=[];swapped=[]
        def opened_at(path,*args,**kwargs):
            opened.append((str(path),kwargs.get('dir_fd')))
            if str(path).startswith('.verification-') and not swapped:
                self.cache.rename(held_cache);self.cache.mkdir(mode=0o700)
                (self.cache/str(path)).write_bytes(foreign_payload)
                (self.cache/(p.sha(self.bytes)+'.archive')).write_bytes(foreign_payload)
                swapped.append(str(path))
                self.assertIsNotNone(kwargs.get('dir_fd'))
            return original_open(path,*args,**kwargs)
        def linked_at(src,dst,**kwargs):
            self.assertEqual(kwargs.get('src_dir_fd'),kwargs.get('dst_dir_fd'))
            self.assertIsNotNone(kwargs.get('src_dir_fd'));self.assertFalse(kwargs['follow_symlinks'])
            links.append((src,dst));return original_link(src,dst,**kwargs)
        with mock.patch.object(os,'open',side_effect=opened_at),mock.patch.object(os,'link',side_effect=linked_at):
            filename,custody=store._verify_artifact('pm4py','invented-viewer',self.grant)
        self.assertEqual((held_cache/filename).read_bytes(),self.bytes)
        self.assertEqual((self.cache/filename).read_bytes(),foreign_payload)
        self.assertEqual((self.cache/swapped[0]).read_bytes(),foreign_payload)
        self.assertEqual(custody,p.stat_record((held_cache/filename).stat()))
        self.assertFalse(list(held_cache.glob('.verification-*')))
        self.assertEqual(len(links),1)
        self.assertTrue(all(not str(path).startswith(str(self.cache)+'/') for path,_ in opened))

    def test_temp_collision_preserves_foreign_leaf_and_does_not_publish(self):
        collision=self.cache/'.verification-fixed';collision.write_bytes(b'FOREIGN');collision.chmod(0o600)
        store=self.store(self.authority)
        with mock.patch.object(p.secrets,'token_hex',return_value='fixed'):
            with self.assertRaises(FileExistsError):store.serve(self.request())
        self.assertEqual(collision.read_bytes(),b'FOREIGN');self.assertFalse(list(self.cache.glob('*.archive')))

    def test_replaced_temp_leaf_is_not_published_or_deleted(self):
        store=self.store(self.authority);original_stat=os.stat;replacement=[]
        def changed(path,*args,**kwargs):
            if str(path).startswith('.verification-') and not replacement:
                fd=kwargs['dir_fd'];os.unlink(path,dir_fd=fd)
                new=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                try:os.write(new,b'FOREIGN')
                finally:os.close(new)
                replacement.append(str(path))
            return original_stat(path,*args,**kwargs)
        with mock.patch.object(os,'stat',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'inode changed'):store.serve(self.request())
        self.assertEqual((self.cache/replacement[0]).read_bytes(),b'FOREIGN')
        self.assertFalse(list(self.cache.glob('*.archive')))

    def test_committed_inventory_remains_unavailable_and_complete(self):
        manifest=json.loads((FOLDER/'source-manifest.json').read_bytes())
        result=p.validator.inspect_packet(manifest,(FOLDER/'requirements.lock').read_bytes(),(FOLDER/'Dockerfile').read_bytes(),(FOLDER/'Dockerfile.dockerignore').read_bytes())
        self.assertEqual((result['artifact_count'],result['total_source_bytes'],result['chunks']),(37,267363376,280))
        self.assertEqual(manifest['product_admission'],'unavailable');self.assertFalse(result['product_admission'])
        self.assertTrue(manifest['unresolved_associations'])

if __name__=='__main__':unittest.main()
