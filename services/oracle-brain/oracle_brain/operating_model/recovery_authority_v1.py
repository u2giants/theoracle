"""Concrete own SQL026 currentness. No recovery grant is issued here.

The original control plane owns all global phase claims. Target imports add
quarantined denials only, after separate actual postrestore installation. Every
SQL send uses the single protected connector/original wall+monotonic window.
Caller records/hashes never replace actual authenticated own-role SQL readback.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import stat
import psycopg
from .contracts import canonical_bytes,digest
from .protected_inputs_v1 import _pinned,_parse
from .protected_sql_connection_v1 import _connection_v1
from .request_deadline_v1 import request_remaining_v1,sql_execute_v1,sql_remaining_v1
from .recovery_contracts_v1 import (
 RecoveryPrivateFileV1,RecoveryStartupConfigV1,RecoverySQLIdentityV1,
 RecoveryDescriptorV1,PostRestoreBindingV1,RecoveryCurrentV1,RecoveryClaimV1,
 RecoveryObservationV1,RecoveryPreclaimRefusalV1,
 parse_recovery_descriptor_v1,parse_post_restore_binding_v1,parse_recovery_startup_v1,parse_backup_custody_v1)

PUBLIC_RECOVERY_SIGNATURES_V1=(
 'oracle2.recovery_current_v1(uuid,timestamptz)',
 'oracle2.claim_recovery_phase_v1(uuid,text,timestamptz)',
 'oracle2.observe_recovery_phase_v1(uuid,text,bytea,timestamptz)',
 'oracle2.import_recovery_denials_v1(uuid,bytea,timestamptz)')
PRIVATE_RECOVERY_SIGNATURES_V1=(
 'oracle2._recovery_json_v1(bytea,integer)',
 'oracle2._recovery_context_v1(uuid,timestamptz)',
 'oracle2._recovery_census_v1(uuid,timestamptz)',
 'oracle2._recovery_operational_denials_v1(uuid[],timestamptz)')

class RecoveryOutcomeUnknownV1(RuntimeError):
    """Possibly committed effect; original claim remains nonrepeatable."""
    automatic_retry_allowed=False


def read_recovery_pin_v1(pin,*,limit=65536):
    if type(pin) is not RecoveryPrivateFileV1:raise TypeError('exact installed recovery private pointer required')
    RecoveryPrivateFileV1.model_validate(pin.model_dump())
    before=Path(pin.path).lstat()
    expected=(pin.device,pin.inode,pin.uid,pin.mode)
    if (before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode))!=expected:raise PermissionError('installed recovery file tuple changed')
    raw=_pinned(pin.path,pin.sha256,limit=limit)
    after=Path(pin.path).lstat()
    if (after.st_dev,after.st_ino,after.st_uid,stat.S_IMODE(after.st_mode))!=expected:raise PermissionError('installed recovery file tuple changed')
    return raw


class ProtectedRecoverySettingsV1:
    """Actual startup files are reread at every boundary; records grant nothing."""
    def __init__(self,config_pin,*,expected_issuer_actor,expected_reviewer_actor):
        if type(config_pin) is not RecoveryPrivateFileV1:raise TypeError('actual independently pinned startup file required')
        if expected_issuer_actor==expected_reviewer_actor:raise PermissionError('independent recovery installation required')
        self.pin=config_pin;self.issuer=expected_issuer_actor;self.reviewer=expected_reviewer_actor
        self._initial=self.current_v1()

    def current_v1(self):
        raw=read_recovery_pin_v1(self.pin)
        config=parse_recovery_startup_v1(raw)
        if (config.issuer_actor,config.reviewer_actor)!=(self.issuer,self.reviewer):raise PermissionError('recovery installer/reviewer differs')
        descriptor_raw=read_recovery_pin_v1(config.descriptor)
        descriptor=parse_recovery_descriptor_v1(descriptor_raw)
        now=datetime.now(timezone.utc)
        if not descriptor.issued_at<=now<min(descriptor.expires_at,descriptor.original_horizon):raise PermissionError('independently current recovery operation expired or not effective')
        profile_raw=None;profile=None
        if config.postrestore_binding is not None:
            profile_raw=read_recovery_pin_v1(config.postrestore_binding)
            profile=parse_post_restore_binding_v1(profile_raw)
            if descriptor.kind!='restore' or (profile.restore_operation_id,profile.original_capture_operation_id,profile.backup_manifest_sha256,profile.descriptor_sha256)!=(descriptor.operation_id,descriptor.original_capture_operation_id,descriptor.backup_manifest_sha256,hashlib.sha256(descriptor_raw).hexdigest()):raise PermissionError('postrestore profile belongs to different operation')
            if (profile.issuer_actor,profile.reviewer_actor)!=(self.issuer,self.reviewer):raise PermissionError('postrestore installation principals differ')
        result=(config,descriptor_raw,descriptor,profile_raw,profile)
        if hasattr(self,'_initial') and result!=self._initial:raise PermissionError('installed recovery settings drifted; no automatic repin')
        return result

    def _custody_file_v1(self):
        """Protected descriptive bytes only; own SQL pin check remains mandatory."""
        config,descriptor_raw,descriptor,_,_=self.current_v1()
        if config.backup_custody is None:raise PermissionError('independently installed backup custody missing')
        raw=read_recovery_pin_v1(config.backup_custody)
        value=parse_backup_custody_v1(raw).bind_descriptive_operation(descriptor)
        if (value.issuer_actor,value.reviewer_actor)!=(self.issuer,self.reviewer):raise PermissionError('backup custody installation principals differ')
        now=datetime.now(timezone.utc)
        if not value.issued_at<=now<min(value.expires_at,value.original_horizon):raise PermissionError('original independent backup custody expired')
        self.current_v1()
        return raw,value

    def _runtime_manifest_file_v1(self):
        """Independently pinned small header; byte census is not loader authority."""
        from .recovery_contracts_v1 import parse_recovery_archive_runtime_manifest_v1
        config,_,descriptor,_,_=self.current_v1()
        if config.archive_runtime_manifest is None:raise PermissionError('independently installed runtime manifest missing')
        custody_raw,custody=self._custody_file_v1()
        raw=read_recovery_pin_v1(config.archive_runtime_manifest)
        value=parse_recovery_archive_runtime_manifest_v1(raw).bind_descriptive_operation(descriptor,custody,hashlib.sha256(custody_raw).hexdigest())
        protected=[self.pin,config.descriptor,config.backup_custody,config.archive_runtime_manifest,value.census]
        for binding in descriptor.purpose_bindings:
            protected.extend((binding.sql_identity.database_url,binding.sql_identity.tls_ca))
        if config.postrestore_binding is not None:protected.append(config.postrestore_binding)
        for pin in protected:
            if any(Path(pin.path).is_relative_to(Path(root.path)) for root in value.installed_roots):raise PermissionError('runtime census must exclude protected configuration and credentials')
        now=datetime.now(timezone.utc)
        if not value.valid_from<=now<min(value.expires_at,value.original_horizon):raise PermissionError('installed runtime evidence expired or not effective')
        self.current_v1()
        return raw,value

    def identity_v1(self,purpose,*,target=False):
        _,_,d,_,p=self.current_v1()
        if target:
            if p is None:raise PermissionError('actual separately installed postrestore target profile missing')
            now=datetime.now(timezone.utc)
            if not p.issued_at<=now<min(p.expires_at,p.original_horizon,p.original_phase_deadline):raise PermissionError('actual postrestore target window elapsed')
            population=p.purpose_bindings
        else:population=d.purpose_bindings
        matches=[v for v in population if v.phase_authority==purpose]
        if len(matches)!=1:raise PermissionError('exact installed recovery purpose binding missing')
        identity=matches[0].sql_identity
        # Actual protected credentials/CA, including file tuple, never defaults.
        raw=read_recovery_pin_v1(identity.database_url,limit=16384)
        read_recovery_pin_v1(identity.tls_ca,limit=1048576)
        try:url=raw.decode('utf-8')
        except UnicodeError:raise PermissionError('exact protected recovery connection bytes required') from None
        if not url or url.strip()!=url or '\x00' in url:raise PermissionError('canonical protected recovery connection required')
        params=psycopg.conninfo.conninfo_to_dict(url)
        if any(params.get(k)!=v for k,v in {'host':identity.host,'hostaddr':identity.hostaddr,'port':str(identity.port),'dbname':identity.database_name,'user':identity.session_role,'sslmode':'verify-full','sslrootcert':identity.tls_ca.path}.items()):raise PermissionError('actual recovery URL differs from installed target/TLS/role')
        return identity,url


# Complete namespace catalog identity, not a caller-provided object census.
# Company rows/passwords/secret values are never selected. OIDs/owners/ACLs,
# columns/constraints/triggers/function bodies/types are all included; any drift
# needs an independently installed new profile, never automatic renewal.
_CATALOG_SQL_V1="""SELECT jsonb_build_object(
 'tables',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',c.oid,'name',c.relname,'owner',c.relowner,'kind',c.relkind,'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'acl',c.relacl::text,
 'columns',(SELECT coalesce(jsonb_agg(jsonb_build_object('number',a.attnum,'name',a.attname,'type',a.atttypid,'modifier',a.atttypmod,'not_null',a.attnotnull,'acl',a.attacl::text,'default',pg_get_expr(ad.adbin,ad.adrelid)) ORDER BY a.attnum),'[]') FROM pg_attribute a LEFT JOIN pg_attrdef ad ON(ad.adrelid,ad.adnum)=(a.attrelid,a.attnum) WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
 'constraints',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',k.oid,'name',k.conname,'definition',pg_get_constraintdef(k.oid),'validated',k.convalidated) ORDER BY k.oid),'[]') FROM pg_constraint k WHERE k.conrelid=c.oid),
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',t.oid,'definition',pg_get_triggerdef(t.oid),'enabled',t.tgenabled) ORDER BY t.oid),'[]') FROM pg_trigger t WHERE t.tgrelid=c.oid),
 'policies',(SELECT coalesce(jsonb_agg(to_jsonb(p) ORDER BY p.oid),'[]') FROM pg_policy p WHERE p.polrelid=c.oid)) ORDER BY c.oid),'[]') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='oracle2'),
 'functions',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',p.oid,'name',p.proname,'owner',p.proowner,'kind',p.prokind,'language',p.prolang,'arguments',p.proargtypes::text,'result',p.prorettype,'security_definer',p.prosecdef,'config',p.proconfig,'volatility',p.provolatile,'acl',p.proacl::text,'body_sha256',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')) ORDER BY p.oid),'[]') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='oracle2'),
 'enums',(SELECT coalesce(jsonb_agg(jsonb_build_object('type',t.oid,'label',e.enumlabel,'order',e.enumsortorder) ORDER BY t.oid,e.enumsortorder),'[]') FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace JOIN pg_enum e ON e.enumtypid=t.oid WHERE n.nspname='oracle2'))"""


def recovery_catalog_fingerprint_v1(connection,deadline):
    if type(connection) is not psycopg.Connection:raise TypeError('actual protected psycopg connection required')
    # Catalog deparsers render visibility-dependent names. Match the actual
    # SQL026 SECURITY DEFINER context within this same original transaction.
    path=sql_execute_v1(connection,deadline,"SELECT pg_catalog.set_config('search_path','pg_catalog, oracle2',true)").fetchone()
    if path!=('pg_catalog, oracle2',):raise PermissionError('fixed recovery catalog rendering context required')
    result=sql_execute_v1(connection,deadline,_CATALOG_SQL_V1).fetchone()
    if result is None or type(result[0]) is not dict:raise PermissionError('actual complete recovery catalog unavailable')
    return digest(result[0])


class RecoverySQLAuthorityV1:
    """Fixed SQL026 owner; factory chooses closed purpose, never request input."""
    def __init__(self,settings,purpose,*,target=False):
        if type(settings) is not ProtectedRecoverySettingsV1 or type(target) is not bool:raise TypeError('actual protected recovery settings required')
        if purpose not in ('capture','current-denials','deny-only-target','observe'):raise PermissionError('closed installed recovery purpose required')
        self.settings=settings;self.purpose=purpose;self.target=target
        self.settings.identity_v1(purpose,target=target)

    def custody_v1(self,*,deadline):
        """Actual original own-role current SQL -> protected bytes -> current SQL.

        This never creates an admission or permits a target/publication effect.
        Caller supplies no custody record, hash, root, container or path.
        """
        if self.target or self.purpose not in ('capture','deny-only-target'):raise PermissionError('original independently appointed custody purpose required')
        before=self.current_v1(deadline=deadline)
        raw,custody=self.settings._custody_file_v1()
        sha=hashlib.sha256(raw).hexdigest()
        if custody.phase_authority!=self.purpose or before.backup_custody_sha256!=sha:raise PermissionError('actual own SQL custody admission pin missing or changed')
        after=self.current_v1(deadline=deadline)
        if (after.admission_id,after.backup_custody_sha256,after.descriptor_sha256)!=(before.admission_id,sha,before.descriptor_sha256):raise PermissionError('current custody admission changed during protected read')
        second,value=self.settings._custody_file_v1()
        if second!=raw or value!=custody:raise PermissionError('protected custody drift after actual SQL')
        request_remaining_v1()
        return raw,custody

    def runtime_census_v1(self,*,deadline):
        """Actual own SQL/custody around read-only bytes; never permits a child.

        Complete future native-loader enforcement remains an independent
        installation prerequisite. No caller record/path/hash is accepted.
        """
        custody_raw,custody=self.custody_v1(deadline=deadline)
        before=self.current_v1(deadline=deadline)
        raw,manifest=self.settings._runtime_manifest_file_v1()
        if manifest.custody_sha256!=hashlib.sha256(custody_raw).hexdigest():raise PermissionError('runtime custody differs from actual admitted bytes')
        result=_observe_installed_runtime_census_v1(manifest,deadline=deadline)
        after=self.current_v1(deadline=deadline)
        second,value=self.settings._runtime_manifest_file_v1()
        final_raw,final_custody=self.custody_v1(deadline=deadline)
        if (before.admission_id,before.descriptor_sha256,before.backup_custody_sha256)!=(after.admission_id,after.descriptor_sha256,after.backup_custody_sha256) or (raw,manifest,custody_raw,custody)!=(second,value,final_raw,final_custody):raise PermissionError('actual runtime/custody admission changed during observation')
        request_remaining_v1();sql_remaining_v1(deadline)
        return manifest,result

    def _check(self,connection,identity,deadline):
        request_remaining_v1()
        row=sql_execute_v1(connection,deadline,"SELECT SESSION_USER,current_database(),(SELECT oid FROM pg_database WHERE datname=current_database()),(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()),current_setting('role'),(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
        if row!=(identity.session_role,identity.database_name,identity.database_oid,identity.database_owner,'none',True):raise PermissionError('actual own recovery role/target/TLS changed')
        if recovery_catalog_fingerprint_v1(connection,deadline)!=identity.schema_catalog_sha256:raise PermissionError('actual complete recovery catalog drifted; quarantine')
        self.settings.identity_v1(self.purpose,target=self.target)
        request_remaining_v1()

    def _call(self,signature,arguments,*,deadline,mutating=False):
        request_remaining_v1();sql_remaining_v1(deadline)
        if type(deadline) is not datetime or deadline.utcoffset() is None or (deadline-datetime.now(timezone.utc)).total_seconds()>30:raise PermissionError('original recovery request <=30 seconds required')
        identity,url=self.settings.identity_v1(self.purpose,target=self.target)
        sent=False
        try:
            with _connection_v1(url,deadline,require_pinned_address=True) as connection:
                self._check(connection,identity,deadline)
                sent=True
                row=sql_execute_v1(connection,deadline,signature,arguments).fetchone()
                self._check(connection,identity,deadline)
            self.settings.identity_v1(self.purpose,target=self.target)
            request_remaining_v1()
            if row is None or type(row[0]) is not dict:raise PermissionError('closed actual SQL026 response required')
            return row[0]
        except Exception as exc:
            if mutating and sent:raise RecoveryOutcomeUnknownV1('possibly written recovery operation; do not retry') from exc
            raise

    def current_v1(self,*,deadline):
        _,raw,d,profile_raw,_=self.settings.current_v1()
        value=self._call('SELECT oracle2.recovery_current_v1(%s,%s)',(d.operation_id,deadline),deadline=deadline)
        result=RecoveryCurrentV1.model_validate_json(canonical_bytes(value))
        if result.descriptor_bytes_hex!=raw.hex() or result.phase_authority!=self.purpose or result.postrestore_binding_bytes_hex!=(profile_raw.hex() if self.target and profile_raw is not None else None):raise PermissionError('actual current recovery input differs from protected startup')
        if result.valid_until>deadline or result.valid_until<=datetime.now(timezone.utc):raise PermissionError('actual current recovery window elapsed')
        return result

    def _claim_v1(self,phase,*,deadline):
        _,_,d,_,_=self.settings.current_v1()
        value=self._call('SELECT oracle2.claim_recovery_phase_v1(%s,%s,%s)',(d.operation_id,phase,deadline),deadline=deadline,mutating=True)
        try:
            result=RecoveryClaimV1.model_validate_json(canonical_bytes(value))
            if (result.operation_id,result.phase,result.descriptor_sha256)!=(d.operation_id,phase,digest(d.model_dump(mode='json'))):raise ValueError('retained recovery claim differs')
            return result
        except Exception as exc:raise RecoveryOutcomeUnknownV1('actual recovery claim response uncertain; do not retry') from exc

    def _import_actual_census_v1(self,census,*,deadline):
        # Private factory-only path. A typed census alone authenticates NOTHING.
        _,_,d,_,_=self.settings.current_v1()
        raw=canonical_bytes(census.model_dump(mode='json'))
        return self._call('SELECT oracle2.import_recovery_denials_v1(%s,%s,%s)',(d.operation_id,raw,deadline),deadline=deadline,mutating=True)

    def _observe_actual_v1(self,observation,*,deadline):
        if type(observation) not in (RecoveryObservationV1,RecoveryPreclaimRefusalV1):raise TypeError('closed actual recovery observation required')
        _,_,d,_,_=self.settings.current_v1()
        phase=observation.phase if type(observation) is RecoveryObservationV1 else observation.attempted_phase
        raw=canonical_bytes(observation.model_dump(mode='json'))
        return self._call('SELECT oracle2.observe_recovery_phase_v1(%s,%s,%s,%s)',(d.operation_id,phase,raw,deadline),deadline=deadline,mutating=True)

# Separate complete native-dump DDL inventory. The existing oracle2-only control
# fingerprint above is deliberately unchanged. No table payload/credential value
# is selected; expression/function/constraint/index definitions are HASHED.
_DUMP_CATALOG_SQL_V1="""SELECT jsonb_build_object(
 'schema_version',1,'protocol','oracle-replacement-native-ddl-inventory-v1',
 'schemas',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',nspname,'owner',nspowner,'acl',nspacl::text) ORDER BY nspname),'[]') FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'),
 'foreign_objects_present',EXISTS(SELECT 1 FROM pg_foreign_server),
 'unsupported_objects_present',(EXISTS(SELECT 1 FROM pg_event_trigger) OR EXISTS(SELECT 1 FROM pg_seclabel) OR EXISTS(SELECT 1 FROM pg_largeobject_metadata) OR EXISTS(SELECT 1 FROM pg_rewrite WHERE rulename<>'_RETURN') OR EXISTS(SELECT 1 FROM pg_cast WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_conversion WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_operator WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_opclass WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_opfamily WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_transform WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_statistic_ext) OR EXISTS(SELECT 1 FROM pg_ts_config WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_ts_dict WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_ts_parser WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_ts_template WHERE oid>=16384) OR EXISTS(SELECT 1 FROM pg_proc WHERE prokind='a' AND oid>=16384)),
 'relations',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'oid',c.oid,'kind',c.relkind,'owner',c.relowner,'acl',c.relacl::text,'row_security',c.relrowsecurity,'force_row_security',c.relforcerowsecurity,'persistence',c.relpersistence,'access_method',c.relam,'tablespace',c.reltablespace,'is_partition',c.relispartition,'replica_identity',c.relreplident,'options',c.reloptions,'partition_bound_sha256',encode(sha256(convert_to(coalesce(pg_get_expr(c.relpartbound,c.oid),''),'UTF8')),'hex'),
 'columns',(SELECT coalesce(jsonb_agg(jsonb_build_object('ordinal',a.attnum,'name',a.attname,'type_schema',tn.nspname,'type_name',t.typname,'type_modifier',a.atttypmod,'collation',a.attcollation,'not_null',a.attnotnull,'dimensions',a.attndims,'storage',a.attstorage,'compression',a.attcompression,'statistics_target',a.attstattarget,'identity',a.attidentity,'generated',a.attgenerated,'acl',a.attacl::text,'default_sha256',encode(sha256(convert_to(coalesce(pg_get_expr(ad.adbin,ad.adrelid),''),'UTF8')),'hex')) ORDER BY a.attnum),'[]') FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid JOIN pg_namespace tn ON tn.oid=t.typnamespace LEFT JOIN pg_attrdef ad ON(ad.adrelid,ad.adnum)=(a.attrelid,a.attnum) WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
 'constraints',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',k.oid,'name',k.conname,'validated',k.convalidated,'definition_sha256',encode(sha256(convert_to(pg_get_constraintdef(k.oid),'UTF8')),'hex')) ORDER BY k.oid),'[]') FROM pg_constraint k WHERE k.conrelid=c.oid),
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',t.oid,'name',t.tgname,'enabled',t.tgenabled,'internal',t.tgisinternal,'definition_sha256',encode(sha256(convert_to(pg_get_triggerdef(t.oid),'UTF8')),'hex')) ORDER BY t.oid),'[]') FROM pg_trigger t WHERE t.tgrelid=c.oid),
 'policies',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',p.oid,'name',p.polname,'command',p.polcmd,'permissive',p.polpermissive,'roles',p.polroles,'using_sha256',encode(sha256(convert_to(coalesce(pg_get_expr(p.polqual,p.polrelid),''),'UTF8')),'hex'),'check_sha256',encode(sha256(convert_to(coalesce(pg_get_expr(p.polwithcheck,p.polrelid),''),'UTF8')),'hex')) ORDER BY p.oid),'[]') FROM pg_policy p WHERE p.polrelid=c.oid),
 'index_sha256',CASE WHEN c.relkind IN('i','I') THEN encode(sha256(convert_to(pg_get_indexdef(c.oid),'UTF8')),'hex') ELSE NULL END,
 'view_sha256',CASE WHEN c.relkind IN('v','m') THEN encode(sha256(convert_to(pg_get_viewdef(c.oid),'UTF8')),'hex') ELSE NULL END,
 'sequence',(SELECT jsonb_build_object('type',s.seqtypid,'start',s.seqstart,'increment',s.seqincrement,'maximum',s.seqmax,'minimum',s.seqmin,'cache',s.seqcache,'cycle',s.seqcycle) FROM pg_sequence s WHERE s.seqrelid=c.oid)) ORDER BY n.nspname,c.relname),'[]') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'),
 'functions',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',p.proname,'oid',p.oid,'owner',p.proowner,'kind',p.prokind,'language',p.prolang,'arguments',p.proargtypes::text,'all_arguments',p.proallargtypes,'argument_modes',p.proargmodes,'result',p.prorettype,'set_result',p.proretset,'security_definer',p.prosecdef,'config_sha256',encode(sha256(convert_to(coalesce(p.proconfig::text,''),'UTF8')),'hex'),'volatility',p.provolatile,'strict',p.proisstrict,'parallel',p.proparallel,'acl',p.proacl::text,'definition_sha256',CASE WHEN p.prokind<>'a' THEN encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex') ELSE NULL END,'body_sha256',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),'binary_sha256',encode(sha256(convert_to(coalesce(p.probin,''),'UTF8')),'hex'),'argument_defaults_sha256',encode(sha256(convert_to(coalesce(pg_get_expr(p.proargdefaults,0),''),'UTF8')),'hex')) ORDER BY n.nspname,p.oid),'[]') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'),
 'types',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',t.typname,'oid',t.oid,'owner',t.typowner,'kind',t.typtype,'catalog_metadata',to_jsonb(t)-'typdefault'-'typdefaultbin','category',t.typcategory,'base',t.typbasetype,'element',t.typelem,'relation',t.typrelid,'not_null',t.typnotnull,'collation',t.typcollation,'acl',t.typacl::text,'default_sha256',encode(sha256(convert_to(coalesce(t.typdefault,''),'UTF8')),'hex'),'enum_labels',(SELECT coalesce(jsonb_agg(jsonb_build_object('label',e.enumlabel,'order',e.enumsortorder) ORDER BY e.enumsortorder),'[]') FROM pg_enum e WHERE e.enumtypid=t.oid)) ORDER BY n.nspname,t.oid),'[]') FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'),
 'extensions',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',e.extname,'owner',e.extowner,'namespace',n.nspname,'version',e.extversion,'relocatable',e.extrelocatable,'configuration_tables',e.extconfig,'condition_sha256',encode(sha256(convert_to(coalesce(e.extcondition::text,''),'UTF8')),'hex')) ORDER BY e.extname),'[]') FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace),
 'collations',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.collname,'owner',c.collowner,'provider',c.collprovider,'deterministic',c.collisdeterministic,'encoding',c.collencoding,'collate',c.collcollate,'ctype',c.collctype,'icu_locale',c.colliculocale,'version',c.collversion) ORDER BY n.nspname,c.oid),'[]') FROM pg_collation c JOIN pg_namespace n ON n.oid=c.collnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'))"""


# Root-ratified exact source020 fingerprint metadata, never auth credentials.
# No suffix/pattern/password-hash exception. Actual full DDL/source pins remain
# mandatory; actual secret/SCRAM/client-key/opaque payload is never admitted.
_NON_CREDENTIAL_SOURCE_COLUMNS_V1=frozenset({
 ('oracle2','meeting_capture_admissions_v1','verifier_secret_sha256'),
 ('oracle2','meeting_capture_admissions_v1','queue_credential_sha256')})

def validate_recovery_dump_catalog_v1(observed,expected_sha256):
    """Descriptive full-record comparison, NOT independently installed authority.

    The concrete owner obtains bytes from exact current native SQL and obtains
    the expected pin only from independently protected actual custody. No caller
    record or metadata hash establishes route, source rights, credentials safety
    of opaque payloads, snapshot consistency or a dump/restore permission.
    """
    import re
    keys={'schema_version','protocol','schemas','foreign_objects_present','unsupported_objects_present','relations','functions','types','extensions','collations'}
    if type(observed) is not dict or set(observed)!=keys or type(observed['schema_version']) is not int or observed['schema_version']!=1 or observed['protocol']!='oracle-replacement-native-ddl-inventory-v1':raise PermissionError('closed complete native DDL catalog required')
    if type(expected_sha256) is not str or re.fullmatch(r'[0-9a-f]{64}',expected_sha256) is None:raise PermissionError('independently installed complete dump inventory pin missing')
    if type(observed['foreign_objects_present']) is not bool or observed['foreign_objects_present'] or type(observed['unsupported_objects_present']) is not bool or observed['unsupported_objects_present']:raise PermissionError('foreign native DDL object quarantine')
    for key in ('schemas','relations','functions','types','extensions','collations'):
        if type(observed[key]) is not list or len(observed[key])>4096:raise PermissionError('complete bounded native DDL population required')
    def closed(value,fields):
        if type(value) is not dict or set(value)!=set(fields.split()):raise PermissionError('missing/unknown native DDL metadata field quarantines participant')
    def exact(item,field,kind):
        if type(item.get(field)) is not kind:raise PermissionError('coerced native DDL metadata refused')
    for item in observed['schemas']:
        closed(item,'name owner acl');exact(item,'name',str);exact(item,'owner',int)

    for item in observed['functions']:closed(item,'schema name oid owner kind language arguments all_arguments argument_modes result set_result security_definer config_sha256 volatility strict parallel acl definition_sha256 body_sha256 binary_sha256 argument_defaults_sha256')
    for item in observed['types']:closed(item,'schema name oid owner kind catalog_metadata category base element relation not_null collation acl default_sha256 enum_labels')
    for item in observed['extensions']:closed(item,'name owner namespace version relocatable configuration_tables condition_sha256')
    for item in observed['collations']:closed(item,'schema name owner provider deterministic encoding collate ctype icu_locale version')
    for item in observed['functions']:
        for field in ('set_result','security_definer','strict'):exact(item,field,bool)
        for field in ('owner','oid','language','result'):exact(item,field,int)
        if item['schema'] not in ('oracle2','public') or item['kind'] not in ('f','p','w'):raise PermissionError('unsupported native function kind/schema')
    for item in observed['types']:
        exact(item,'not_null',bool)
        if item['schema'] not in ('oracle2','public') or item['kind'] not in ('b','c','e'):raise PermissionError('unsupported native type/domain quarantine')
    for item in observed['extensions']:exact(item,'relocatable',bool)
    for item in observed['collations']:exact(item,'deterministic',bool)
    if {v.get('name') for v in observed['schemas']}!={'oracle2','public'}:raise PermissionError('unsupported/authentication schema quarantines participant')
    if len(observed['schemas'])!=2:raise PermissionError('duplicate native schema census')
    forbidden=r'(^|_)(password|passwd|secret|credential|credentials|private_key|client_key|tls_key|sslkey|sslcert|dsn|connection_string|database_url)($|_)'
    seen=set();tables=[]
    for relation in observed['relations']:
        if type(relation) is not dict or relation.get('schema') not in ('oracle2','public') or relation.get('kind') not in ('r','p','S','i','I','v','m','c'):raise PermissionError('unknown native relation kind/schema quarantines participant')
        closed(relation,'schema name oid kind owner acl row_security force_row_security persistence access_method tablespace is_partition replica_identity options partition_bound_sha256 columns constraints triggers policies index_sha256 view_sha256 sequence')
        for field in ('row_security','force_row_security','is_partition'):exact(relation,field,bool)
        for field in ('oid','owner','access_method','tablespace'):exact(relation,field,int)
        for field,shape in (('constraints','oid name validated definition_sha256'),('triggers','oid name enabled internal definition_sha256'),('policies','oid name command permissive roles using_sha256 check_sha256')):
            if type(relation[field]) is not list or len(relation[field])>4096:raise PermissionError('complete bounded native relation DDL population required')
            for item in relation[field]:closed(item,shape)
        if relation['sequence'] is not None:closed(relation['sequence'],'type start increment maximum minimum cache cycle')
        name=relation.get('name')
        if type(name) is not str or re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,62}',name) is None or re.search(forbidden,name,re.I):raise PermissionError('unsupported credential-bearing relation quarantines participant')
        identity=(relation['schema'],name)
        if identity in seen:raise PermissionError('duplicate native relation census')
        seen.add(identity)
        if relation['kind'] in ('r','p'):tables.append(relation['schema']+'.'+name)
        columns=relation.get('columns')
        if type(columns) is not list or len(columns)>1600:raise PermissionError('complete bounded native columns required')
        for column in columns:
            closed(column,'ordinal name type_schema type_name type_modifier collation not_null dimensions storage compression statistics_target identity generated acl default_sha256')
            exact(column,'not_null',bool)
            for field in ('ordinal','type_modifier','collation','dimensions','statistics_target'):exact(column,field,int)
            source_hash=(relation['schema'],name,column.get('name')) in _NON_CREDENTIAL_SOURCE_COLUMNS_V1
            if source_hash and (column.get('type_schema'),column.get('type_name'))!=('pg_catalog','text'):raise PermissionError('exact source fingerprint metadata type changed')
            if type(column) is not dict or type(column.get('name')) is not str or re.search(forbidden,column['name'],re.I) and not source_hash or column.get('type_schema') not in ('pg_catalog','oracle2','public'):raise PermissionError('unknown/credential-bearing column quarantines participant')
    # Full hash includes ALL actual closed-builder output: owner, RLS/ACL,
    # typmods/collations/identity/generated/defaults, constraints, triggers,
    # policies, functions/body/security, sequences and every supported DDL item.
    # A name scan alone never suffices, nor can it certify opaque checkpoint data.
    if digest(observed)!=expected_sha256:raise PermissionError('complete independently pinned native DDL inventory changed')
    return tuple(sorted(tables))

def _observe_installed_runtime_census_v1(manifest,*,deadline):
    """Read-only actual listed-byte census; NEVER native-loader qualification.

    Small canonical records use the existing parser. Complete actual source
    roots are streamed; retained metadata is finite fixed-size path digests and
    stat tuples, not whole census JSON or runtime file bodies. No child starts.
    """
    import os
    from .recovery_contracts_v1 import (RecoveryArchiveRuntimeManifestV1,
      RecoveryRuntimeCensusRecordV1,RUNTIME_CENSUS_LINE_LIMIT_V1,RUNTIME_CENSUS_MAX_FILES_V1)
    if type(manifest) is not RecoveryArchiveRuntimeManifestV1:raise TypeError('exact installed runtime header required')
    RecoveryArchiveRuntimeManifestV1.model_validate(manifest.model_dump())
    def fresh():
        request_remaining_v1();sql_remaining_v1(deadline)
        if not manifest.valid_from<=datetime.now(timezone.utc)<min(manifest.expires_at,manifest.original_horizon):raise PermissionError('installed runtime window expired or not effective')
    def exact_stat(info,pin):
        return stat.S_ISREG(info.st_mode) and info.st_nlink==1 and(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_size)==(pin.device,pin.inode,pin.uid,pin.mode,pin.size)
    def unchanged(a,b):return(a.st_dev,a.st_ino,a.st_uid,a.st_mode,a.st_size,a.st_nlink,a.st_mtime_ns,a.st_ctime_ns)==(b.st_dev,b.st_ino,b.st_uid,b.st_mode,b.st_size,b.st_nlink,b.st_mtime_ns,b.st_ctime_ns)
    def actual_root(root):
        fresh();path=Path(root.path)
        if path.resolve()!=path:raise PermissionError('installed runtime root must not traverse links')
        info=path.lstat()
        if not stat.S_ISDIR(info.st_mode) or(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))!=(root.device,root.inode,root.uid,root.mode):raise PermissionError('actual installed runtime root differs')
        return info
    fresh()
    pages=os.sysconf('SC_AVPHYS_PAGES');page_size=os.sysconf('SC_PAGE_SIZE')
    if type(pages) is not int or type(page_size) is not int or pages<=0 or page_size<=0 or pages*page_size<manifest.memory_limit_bytes+manifest.memory_headroom_bytes:raise PermissionError('actual available memory cannot cover independently installed runtime allowance')
    roots={v.path:actual_root(v) for v in manifest.installed_roots}
    pin=manifest.census;path=Path(pin.path)
    if path.resolve()!=path:raise PermissionError('protected runtime census must not traverse links')
    initial=path.lstat();expected=(pin.device,pin.inode,pin.uid,pin.mode)
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink!=1 or initial.st_size!=manifest.census_bytes or(initial.st_dev,initial.st_ino,initial.st_uid,stat.S_IMODE(initial.st_mode))!=expected:raise PermissionError('actual protected runtime census differs')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    observed={};inodes=set();wire_hash=hashlib.sha256();wire_bytes=0;file_bytes=0;count=0;previous=None;special=set()
    try:
        if not unchanged(initial,os.fstat(fd)):raise PermissionError('runtime census changed before streaming')
        with os.fdopen(os.dup(fd),'rb') as stream:
            while True:
                fresh();raw=stream.readline(RUNTIME_CENSUS_LINE_LIMIT_V1+1)
                if not raw:break
                if len(raw)>RUNTIME_CENSUS_LINE_LIMIT_V1+1 or not raw.endswith(b'\n') or raw==b'\n' or raw.endswith(b'\r\n'):raise PermissionError('bounded canonical newline runtime record required')
                count+=1;wire_bytes+=len(raw)
                if count>manifest.file_count or wire_bytes>manifest.census_bytes:raise PermissionError('runtime census count/bytes exceeded')
                record=_parse(RecoveryRuntimeCensusRecordV1,raw[:-1]);item=record.file
                if record.sequence!=count or previous is not None and item.path<=previous:raise PermissionError('runtime records must be unique exactly sorted sequence')
                previous=item.path
                matching=[r for r in manifest.installed_roots if Path(item.path).is_relative_to(Path(r.path))]
                if len(matching)!=1 or item.device!=matching[0].device:raise PermissionError('runtime file outside exact installed filesystem root')
                if (item.device,item.inode) in inodes:raise PermissionError('runtime file identity appears more than once')
                file_bytes+=item.size
                if file_bytes>manifest.total_file_bytes:raise PermissionError('runtime file aggregate exceeded')
                file_path=Path(item.path);fresh()
                if file_path.resolve()!=file_path:raise PermissionError('runtime file path traverses a link')
                actual_fd=os.open(file_path,os.O_RDONLY|os.O_NOFOLLOW)
                try:
                    before=os.fstat(actual_fd)
                    if not exact_stat(before,item):raise PermissionError('actual installed runtime file tuple differs')
                    actual_hash=hashlib.sha256();actual_bytes=0
                    while True:
                        fresh();chunk=os.read(actual_fd,65536)
                        if not chunk:break
                        actual_bytes+=len(chunk)
                        if actual_bytes>item.size:raise PermissionError('runtime file grew beyond pin')
                        actual_hash.update(chunk)
                    fresh();after=os.fstat(actual_fd)
                    if actual_bytes!=item.size or actual_hash.hexdigest()!=item.sha256 or not unchanged(before,after) or not unchanged(after,file_path.lstat()):raise PermissionError('actual installed runtime bytes changed')
                finally:os.close(actual_fd)
                if item.path==manifest.interpreter.path:
                    if item!=manifest.interpreter:raise PermissionError('interpreter census binding differs')
                    special.add('interpreter')
                if item.path==manifest.entrypoint.path:
                    if item!=manifest.entrypoint:raise PermissionError('entrypoint census binding differs')
                    special.add('entrypoint')
                # Digest-keyed exact census membership avoids storing all paths.
                name_hash=hashlib.sha256(item.path.encode('utf-8')).digest()
                if name_hash in observed:raise PermissionError('duplicate runtime path digest refused')
                observed[name_hash]=after;inodes.add((item.device,item.inode));wire_hash.update(raw)
        fresh()
        if(count,wire_bytes,file_bytes)!=(manifest.file_count,manifest.census_bytes,manifest.total_file_bytes) or wire_hash.hexdigest()!=pin.sha256 or special!={'interpreter','entrypoint'}:raise PermissionError('complete exact runtime census differs')
        if not unchanged(initial,os.fstat(fd)) or not unchanged(initial,path.lstat()):raise PermissionError('runtime census drift after streaming')
    finally:os.close(fd)
    actual_count=0;directories=0
    def walk(directory_fd,directory_path,root,depth=0):
        nonlocal actual_count,directories
        fresh();directories+=1
        if depth>128 or directories>2*RUNTIME_CENSUS_MAX_FILES_V1+32:raise PermissionError('runtime directory traversal bound exceeded')
        initial_directory=os.fstat(directory_fd)
        if not stat.S_ISDIR(initial_directory.st_mode) or initial_directory.st_dev!=root.device or initial_directory.st_mode&0o022:raise PermissionError('actual installed directory differs')
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                fresh();info=entry.stat(follow_symlinks=False);full_path=str(Path(directory_path)/entry.name)
                if entry.is_symlink() or info.st_dev!=root.device:raise PermissionError('runtime root contains symlink or unknown mounted filesystem')
                if stat.S_ISDIR(info.st_mode):
                    child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory_fd)
                    try:
                        actual=os.fstat(child)
                        if(actual.st_dev,actual.st_ino,actual.st_uid,actual.st_mode)!=(info.st_dev,info.st_ino,info.st_uid,info.st_mode):raise PermissionError('runtime directory changed before traversal')
                        walk(child,full_path,root,depth+1)
                    finally:os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    actual_count+=1
                    if actual_count>manifest.file_count:raise PermissionError('extra actual runtime file')
                    expected_file=observed.get(hashlib.sha256(full_path.encode('utf-8')).digest())
                    if expected_file is None or not unchanged(expected_file,info):raise PermissionError('unlisted or changed actual installed file')
                else:raise PermissionError('unknown runtime filesystem object refused')
        final_directory=os.fstat(directory_fd)
        if(initial_directory.st_dev,initial_directory.st_ino,initial_directory.st_uid,initial_directory.st_mode,initial_directory.st_mtime_ns,initial_directory.st_ctime_ns)!=(final_directory.st_dev,final_directory.st_ino,final_directory.st_uid,final_directory.st_mode,final_directory.st_mtime_ns,final_directory.st_ctime_ns):raise PermissionError('runtime directory changed during traversal')
    for root in manifest.installed_roots:
        root_fd=os.open(root.path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            actual=os.fstat(root_fd)
            if(actual.st_dev,actual.st_ino,actual.st_uid,stat.S_IMODE(actual.st_mode))!=(root.device,root.inode,root.uid,root.mode):raise PermissionError('installed root changed before traversal')
            walk(root_fd,root.path,root)
        finally:os.close(root_fd)
    if actual_count!=manifest.file_count:raise PermissionError('missing actual runtime file')
    for root in manifest.installed_roots:
        before=roots[root.path];after=actual_root(root)
        if(before.st_dev,before.st_ino,before.st_uid,before.st_mode,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_uid,after.st_mode,after.st_mtime_ns,after.st_ctime_ns):raise PermissionError('installed runtime root changed during census')
    fresh()
    return {'manifest_record_sha256':digest(manifest.model_dump(mode='json')),'census_sha256':wire_hash.hexdigest(),
      'file_count':count,'total_file_bytes':file_bytes,'listed_files_verified':True,
      'native_loader_enforced':False,'runtime_qualified':False,'child_invocation_authorized':False,
      'serving_authorized':False,'dispatch_authorized':False,'automatic_retry_allowed':False}
