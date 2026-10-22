"""Protected metadata refusal and controlled boundary order; no native proof."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import hashlib,os

import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.original_source_authority_v1 import OriginalPopulationSnapshotV1
from oracle_brain.hosting import raw_original_settings_v1 as m
from test_raw_original_context_v1 import context


def config():
    x=context();now=datetime.now(timezone.utc)
    def f(name):return {'path':'/private/invented/'+name,'sha256':'a'*64}
    return m.RawOriginalProviderConfigV1(population=x.population,actor_id=x.actor_id,
        phase_purpose=x.job.purpose,expected_owner_role='invented_owner',expected_session_role=x.expected_session_role,
        original_allocation_hash=x.original_allocation_hash,original_horizon=x.original_horizon,
        database_url=f('sql'),database_ca=f('ca'),database_hostname='invented.invalid',database_port=5432,
        database_name='invented',context=f('context'),observer_admission=f('observer'),
        observer_tls={'hostname':'invented.invalid','port':8443,'server_uri':'spiffe://oracle/invented-observer',
            'client_uri':'spiffe://oracle/invented-reader','ca':f('observer-ca'),'certificate':f('cert'),'key':f('key')},
        observer_spool='/private/invented/spool',observer_namespace='raw-reader',observer_initialization_hash='a'*64,
        original_root='/private/invented/originals',original_root_identity=(1,2,os.getuid()),storage_profile_hash='b'*64,
        vision_policy=f('vision'),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),
        expires_at=x.phase_expires_at)


def appointment(c,seal):
    return m.RawOriginalProviderAppointmentV1(config_sha256=seal,context_sha256=c.context.sha256,
        population=c.population,actor_id=c.actor_id,expected_session_role=c.expected_session_role,
        original_allocation_hash=c.original_allocation_hash,original_horizon=c.original_horizon,
        issuer_actor=c.issuer_actor,reviewer_actor=c.reviewer_actor,valid_from=c.valid_from,expires_at=c.expires_at)


def write(path,value):
    raw=canonical_bytes(value.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('field',['config_sha256','context_sha256','actor_id','population','expected_session_role','issuer_actor','expires_at'])
def test_foreign_appointment_refuses_before_any_sql_or_other_private_file(tmp_path,monkeypatch,field):
    c=config();cp=tmp_path/'config';ch=write(cp,c);a=appointment(c,ch);body=a.model_dump(mode='python')
    if field in {'config_sha256','context_sha256'}:body[field]='0'*64
    elif field in {'actor_id','issuer_actor'}:body[field]=uuid4()
    elif field=='population':body[field]['population_id']=uuid4()
    elif field=='expected_session_role':body[field]='foreign_login'
    else:body[field]=datetime.now(timezone.utc)-timedelta(seconds=1)
    a=m.RawOriginalProviderAppointmentV1.model_validate(body);ap=tmp_path/'appointment';ah=write(ap,a)
    seen=[];read=m._worker_file
    def only_metadata(path,*args,**kwargs):
        seen.append(Path(path));assert Path(path) in {cp,ap},'private credential read before appointment'
        return read(path,*args,**kwargs)
    monkeypatch.setattr(m,'_worker_file',only_metadata)
    from oracle_brain.hosting import purpose_journey_v2
    monkeypatch.setattr(purpose_journey_v2,'_worker_file',only_metadata)
    with pytest.raises(PermissionError):m.load_raw_original_provider_settings_v1(cp,ch,appointment_path=ap,
        expected_appointment_sha256=ah,issuer_actor=c.issuer_actor,reviewer_actor=c.reviewer_actor)
    assert seen==[cp,ap]


@pytest.mark.parametrize('bad',[True,1.0,'1',2])
def test_closed_config_and_appointment_versions(bad):
    c=config();a=appointment(c,digest(c.model_dump(mode='json')))
    for value,cls in ((c,m.RawOriginalProviderConfigV1),(a,m.RawOriginalProviderAppointmentV1)):
        body=value.model_dump(mode='python');body['schema_version']=bad
        with pytest.raises(ValueError):cls.model_validate(body)


def test_current_window_separates_fresh_witness_from_true_original_horizon():
    c=config();now=datetime.now(timezone.utc);events=[]
    snapshot=OriginalPopulationSnapshotV1(population=c.population,original_allocation_hash=c.original_allocation_hash,
        original_horizon=c.original_horizon,actual_principal_id=c.actor_id,session_role=c.expected_session_role,
        checked_at=now,valid_until=c.expires_at)
    class SQL:
        def original_population_current_v1(self,p):events.append('sql');assert p==c.population.population_id;return snapshot
    class Observer:
        admission=SimpleNamespace(expires_at=c.expires_at)
        def current(self,p):
            events.append('observer');assert p==c.population
            return SimpleNamespace(expires_at=now+timedelta(seconds=4),model_dump=lambda **_: {'invented':'witness'})
    window=m._current_window(c,SQL(),Observer(),c.expires_at)
    assert events==['sql','observer','sql']
    assert window.current_until==now+timedelta(seconds=4)
    assert window.operation_horizon==c.expires_at


def test_current_window_revocation_after_observer_denies():
    c=config();now=datetime.now(timezone.utc);events=[]
    snapshot=OriginalPopulationSnapshotV1(population=c.population,original_allocation_hash=c.original_allocation_hash,
        original_horizon=c.original_horizon,actual_principal_id=c.actor_id,session_role=c.expected_session_role,
        checked_at=now,valid_until=c.expires_at)
    class SQL:
        def original_population_current_v1(self,p):
            events.append('sql')
            if len(events)>1:raise PermissionError('invented third source revoked')
            return snapshot
    class Observer:
        def current(self,p):events.append('observer');return None
    with pytest.raises(PermissionError,match='third source revoked'):
        m._current_window(c,SQL(),Observer(),c.expires_at)
    assert events==['sql','observer','sql']


from test_raw_original_observer_v1 import observed_exchange,bound_tls,certificates


def snapshot_for(c,*,at=None):
    return OriginalPopulationSnapshotV1(population=c.population,original_allocation_hash=c.original_allocation_hash,
        original_horizon=c.original_horizon,actual_principal_id=c.actor_id,session_role=c.expected_session_role,
        checked_at=at or datetime.now(timezone.utc),valid_until=c.expires_at)


def observed_config(consumer):
    original=config()
    return original.model_copy(update={'population':consumer.admission.population,'actor_id':consumer.admission.principal_id,
        'expires_at':min(original.expires_at,consumer.admission.expires_at)})


def test_observed_window_captures_actual_snapshots_and_signed_tls_bytes_without_sql_lock(observed_exchange):
    cns,state,_=observed_exchange;c=observed_config(cns);events=[];snapshots=[];active=[]
    class SQL:
        def original_population_current_v1(self,p,**kwargs):
            assert p==c.population.population_id and kwargs=={}
            active.append('owned getter');events.append('sql-enter')
            try:
                snapshot=snapshot_for(c);snapshots.append(snapshot);return snapshot
            finally:active.pop();events.append('sql-exit')
    def network():assert not active;events.append('network')
    state['network_hook']=network
    result=m._observed_current_window(c,SQL(),cns,c.expires_at)
    assert events==['sql-enter','sql-exit','network','sql-enter','sql-exit']
    assert result.before_snapshot_bytes==canonical_bytes(snapshots[0].model_dump(mode='json'))
    assert result.after_snapshot_bytes==canonical_bytes(snapshots[1].model_dump(mode='json'))
    assert result.before_snapshot_bytes!=result.after_snapshot_bytes
    assert result.observer_evidence.raw_envelope==state['raw'][0]
    assert result.window.sql_receipt_hash==hashlib.sha256(result.after_snapshot_bytes).hexdigest()
    assert result.window.observer_witness_hash==hashlib.sha256(result.observer_evidence.witness_bytes).hexdigest()
    assert result.before_snapshot==snapshots[0] and result.after_snapshot==snapshots[1]
    assert result.window.operation_horizon==c.expires_at
    assert result.window.current_until==result.observer_evidence.witness.expires_at
    assert cns.replay._read()['sequence']==13


def test_observed_window_after_network_revocation_returns_no_window(observed_exchange):
    cns,state,_=observed_exchange;c=observed_config(cns);calls=[]
    class SQL:
        def original_population_current_v1(self,p):
            calls.append(p)
            if len(calls)==2:raise PermissionError('invented current SQL revocation')
            return snapshot_for(c)
    with pytest.raises(PermissionError,match='current SQL revocation'):
        m._observed_current_window(c,SQL(),cns,c.expires_at)
    assert len(calls)==2 and len(state['requests'])==1 and cns.replay._read()['sequence']==13


@pytest.mark.parametrize('damage',['valid','population','actor','session','allocation','horizon','expired-phase'])
def test_both_window_paths_share_exact_pin_and_horizon_rules(observed_exchange,damage):
    from types import SimpleNamespace
    cns,state,_=observed_exchange;c=observed_config(cns)
    observed=cns.observed_current(c.population);now=datetime.now(timezone.utc)
    before=snapshot_for(c);after=before
    phase=c.expires_at
    if damage=='expired-phase':phase=now-timedelta(seconds=1)
    elif damage!='valid':
        key={'population':'population','actor':'actual_principal_id','session':'session_role',
            'allocation':'original_allocation_hash','horizon':'original_horizon'}[damage]
        value=(c.population.model_copy(update={'population_id':uuid4()}) if damage=='population' else
            uuid4() if damage=='actor' else 'foreign' if damage=='session' else '0'*64 if damage=='allocation' else
            c.original_horizon+timedelta(seconds=1))
        after=after.model_copy(update={key:value})
    class SQL:
        def __init__(self):self.calls=0
        def original_population_current_v1(self,p):
            self.calls+=1;return before if self.calls==1 else after
    class Observer:
        admission=cns.admission
        def current(self,p):assert p==c.population;return observed.witness
        def observed_current(self,p):assert p==c.population;return observed
    results=[]
    for function in (m._current_window,m._observed_current_window):
        try:
            result=function(c,SQL(),Observer(),phase)
            results.append(result.window if type(result) is m.RawOriginalObservedAuthorityWindowV1 else result)
        except PermissionError:results.append(PermissionError)
    if damage=='valid':assert results[0]==results[1]
    else:assert results==[PermissionError,PermissionError]


def test_observed_window_rejects_altered_snapshot_envelope_and_hash_bytes(observed_exchange):
    from dataclasses import replace,FrozenInstanceError
    cns,state,_=observed_exchange;c=observed_config(cns)
    class SQL:
        def original_population_current_v1(self,p):return snapshot_for(c)
    result=m._observed_current_window(c,SQL(),cns,c.expires_at)
    changed=__import__('json').loads(result.after_snapshot_bytes)
    changed['actual_principal_id']=str(uuid4())
    for changes in ({'before_snapshot_bytes':result.before_snapshot_bytes+b'\n'},
        {'after_snapshot_bytes':canonical_bytes(changed)}, {'after_snapshot_bytes':b'{}'},
        {'window':replace(result.window,sql_receipt_hash='0'*64)},
        {'window':replace(result.window,observer_witness_hash='0'*64)},
        {'observed_at':result.window.current_until},{'observer_evidence':object()}):
        with pytest.raises((PermissionError,ValueError)):replace(result,**changes)
    with pytest.raises(FrozenInstanceError):result.after_snapshot_bytes=b'changed'


def configured_window_settings(consumer,tmp_path,monkeypatch):
    """Real pinned invented metadata/TLS, typed SQL getter seam; no SQL IO."""
    from test_raw_vision_policy_v1 import packet
    _,policy,_,_,_=packet();x=context();a=consumer.admission
    phase=min(x.phase_expires_at,a.expires_at,policy.expires_at)
    policy=policy.model_copy(update={'expires_at':phase})
    pp=tmp_path/'observed-policy.json';ph=write(pp,policy)
    q=x.job.pricing.model_copy(update={'population_id':a.population.population_id,
        'original_root_hash':a.population.original_root_hash,'vision_token_policy_sha256':ph,'expires_at':phase})
    job=type(x.job).model_validate(x.job.model_dump(mode='python')|{'workspace_id':a.population.workspace_id,
        'population_id':a.population.population_id,'operation_registry_hash':a.population.operation_registry_hash,
        'raw_ref':a.population.raw_refs[0],'pricing':q})
    x=type(x).model_validate(x.model_dump(mode='python')|{'actor_id':a.principal_id,'population':a.population,
        'job':job,'phase_expires_at':phase,'pricing_quote_hash':digest(q.model_dump(mode='json')),
        'vision_token_policy_hash':ph})
    xp=tmp_path/'observed-context.json';xh=write(xp,x)
    op=tmp_path/'observed-admission.json';oh=write(op,a)
    # Copy only invented fixture TLS material so each mutation test owns its
    # exact files and cannot alter the module-scoped certificate fixture.
    original_tls=consumer.transport.binding
    def material(name,data):
        path=tmp_path/name;path.write_bytes(data);path.chmod(0o600)
        return m.RawPrivateFileV1(path=str(path),sha256=hashlib.sha256(data).hexdigest())
    ca=material('observed-tls-ca.pem',original_tls.ca_file.read_bytes())
    cert=material('observed-tls-client.pem',original_tls.certificate_file.read_bytes())
    key=material('observed-tls-client.key',original_tls.key_file.read_bytes())
    tls=m.RawObserverTLSV1(hostname=original_tls.hostname,port=original_tls.port,
        server_uri=original_tls.server_uri,client_uri=original_tls.client_uri,ca=ca,certificate=cert,key=key)
    binding=m.PurposeTLSBindingV2(tls.hostname,tls.port,tls.server_uri,tls.client_uri,
        Path(ca.path),Path(cert.path),Path(key.path),timeout=5)
    consumer.transport=m.RawOriginalObserverClientV1(binding)
    dbca=material('observed-db-ca.pem',b'invented-database-CA-no-connection')
    from psycopg.conninfo import make_conninfo
    own_url=make_conninfo(host='invented.invalid',port=5432,dbname='invented',user=x.expected_session_role,
        password='invented-db-only',sslmode='verify-full',sslrootcert=dbca.path)
    db=material('observed-db-url',own_url.encode())
    c=config();c=type(c).model_validate(c.model_dump(mode='python')|{'actor_id':a.principal_id,
        'population':a.population,'expected_session_role':x.expected_session_role,
        'original_allocation_hash':x.original_allocation_hash,'original_horizon':x.original_horizon,
        'expires_at':phase,'context':m.RawPrivateFileV1(path=str(xp),sha256=xh),
        'vision_policy':m.RawPrivateFileV1(path=str(pp),sha256=ph),
        'observer_admission':m.RawPrivateFileV1(path=str(op),sha256=oh),
        'observer_tls':tls,'database_url':db,'database_ca':dbca})
    cp=tmp_path/'observed-config.json';ch=write(cp,c);app=appointment(c,ch)
    ap=tmp_path/'observed-appointment.json';ah=write(ap,app)
    binding=m.OriginalSourceBindingV1(c.population,c.actor_id,c.phase_purpose,c.expected_owner_role,
        c.expected_session_role,c.original_allocation_hash,c.original_horizon,c.expires_at)
    resolver=object.__new__(m.OriginalSourceResolverV1);resolver.binding=binding;resolver.url=own_url;reads=[]
    def getter(population_id,**kwargs):
        assert population_id==c.population.population_id and kwargs=={}
        result=snapshot_for(c);reads.append(result);return result
    monkeypatch.setattr(resolver,'original_population_current_v1',getter)
    result=m.RawOriginalProviderSettingsV1(c,cp,ch,ap,ah,app,resolver,consumer,x,policy)
    return result,reads


def test_public_old_and_observed_windows_revalidate_same_pinned_settings(observed_exchange,tmp_path,monkeypatch):
    from dataclasses import replace
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    old=settings.current_window();observed=settings.observed_window()
    assert type(old) is m.RawOriginalAuthorityWindowV1 and type(observed) is m.RawOriginalObservedAuthorityWindowV1
    assert len(reads)==4 and len(state['requests'])==2
    assert old.operation_horizon==observed.window.operation_horizon==settings.config.expires_at
    # Actual pinned metadata bytes are mandatory before any SQL/TLS exchange.
    before=(len(reads),len(state['requests']))
    Path(settings.config.context.path).write_bytes(Path(settings.config.context.path).read_bytes()+b'\n')
    for method in (settings.current_window,settings.observed_window):
        with pytest.raises(PermissionError):method()
    assert (len(reads),len(state['requests']))==before


@pytest.mark.parametrize('damage',['resolver','binding','context','appointment','observer-type'])
def test_current_settings_type_and_internal_pin_transplants_deny_both_paths_before_io(observed_exchange,tmp_path,monkeypatch,damage):
    from dataclasses import replace
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    if damage=='resolver':settings=replace(settings,resolver=object())
    elif damage=='binding':settings.resolver.binding=replace(settings.resolver.binding,expected_session_role='foreign_role')
    elif damage=='context':settings=replace(settings,context=settings.context.model_copy(update={'actor_id':uuid4()}))
    elif damage=='appointment':settings=replace(settings,appointment=settings.appointment.model_copy(update={'config_sha256':'0'*64}))
    else:settings=replace(settings,observer=object())
    for method in (settings.current_window,settings.observed_window):
        with pytest.raises(PermissionError):method()
    assert reads==[] and state['requests']==[]


@pytest.mark.parametrize('observed',[False,True])
def test_pinned_context_changed_during_actual_tls_never_returns_window(observed_exchange,tmp_path,monkeypatch,observed):
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    def changed():
        path=Path(settings.config.context.path);path.write_bytes(path.read_bytes()+b'\n')
    state['network_hook']=changed
    with pytest.raises(PermissionError):
        (settings.observed_window if observed else settings.current_window)()
    assert len(reads)==2 and len(state['requests'])==1 and consumer.replay._read()['sequence']==13


@pytest.mark.parametrize('field',['database_url','database_ca','observer_admission','observer_ca','observer_cert','observer_key'])
def test_each_changed_protected_file_refuses_both_current_paths_before_sql_tls(observed_exchange,tmp_path,monkeypatch,field):
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    settings._current_settings_pins()  # The actual loaded fixture pins start valid.
    c=settings.config
    file={'database_url':c.database_url,'database_ca':c.database_ca,'observer_admission':c.observer_admission,
        'observer_ca':c.observer_tls.ca,'observer_cert':c.observer_tls.certificate,'observer_key':c.observer_tls.key}[field]
    path=Path(file.path);path.write_bytes(path.read_bytes()+b'\n')
    for method in (settings.current_window,settings.observed_window):
        with pytest.raises(PermissionError):method()
    assert reads==[] and state['requests']==[]


@pytest.mark.parametrize('field',['hostname','port','server_uri','client_uri','ca_file','certificate_file','key_file','timeout','resolver_url'])
def test_changed_loaded_transport_or_sql_url_refuses_both_paths_before_io(observed_exchange,tmp_path,monkeypatch,field):
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    settings._current_settings_pins()
    if field=='resolver_url':settings.resolver.url+=' application_name=foreign'
    else:
        binding=consumer.transport.binding
        value=('foreign.invalid' if field=='hostname' else binding.port+1 if field=='port' else
            'spiffe://oracle/foreign' if field in {'server_uri','client_uri'} else
            Path(binding.ca_file.parent/'unconfigured-material') if field.endswith('_file') else 4)
        # Simulate post-startup object drift without issuing a new binding.
        object.__setattr__(binding,field,value)
    for method in (settings.current_window,settings.observed_window):
        with pytest.raises(PermissionError):method()
    assert reads==[] and state['requests']==[]


@pytest.mark.parametrize('field',['database_url','database_ca','observer_admission','observer_ca','observer_cert','observer_key','loaded_binding'])
@pytest.mark.parametrize('observed',[False,True])
def test_protected_material_or_binding_drift_during_tls_never_returns_evidence(observed_exchange,tmp_path,monkeypatch,field,observed):
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    c=settings.config
    def changed():
        if field=='loaded_binding':object.__setattr__(consumer.transport.binding,'timeout',4);return
        file={'database_url':c.database_url,'database_ca':c.database_ca,'observer_admission':c.observer_admission,
            'observer_ca':c.observer_tls.ca,'observer_cert':c.observer_tls.certificate,'observer_key':c.observer_tls.key}[field]
        path=Path(file.path);path.write_bytes(path.read_bytes()+b'\n')
    state['network_hook']=changed
    with pytest.raises(PermissionError):
        (settings.observed_window if observed else settings.current_window)()
    assert len(reads)==2 and len(state['requests'])==1 and consumer.replay._read()['sequence']==13


def billing_settings(observed_exchange,tmp_path,monkeypatch,*,raw_transform=None,bounds_update=None,shared_only=False):
    """Appointed invented canonical billing file; no provider or SQL requests."""
    from dataclasses import replace
    from decimal import Decimal
    consumer,state,_=observed_exchange
    settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    q=settings.context.job.pricing
    # The retained generic quote fixture predates exact billing identity. Pin an
    # actual consistent invented quote/context rather than loosening assertions.
    fp=settings.context.job.processing_request.account.removeprefix('key-sha256:')
    changes={'key_fingerprint':fp,'terms_hash':settings.context.job.processing_request.terms_hash}
    if shared_only:
        changes.update(is_byok=False,**{key:Decimal('0') for key in ('upstream_input_per_million_usd',
            'upstream_output_per_million_usd','upstream_per_image_fee_usd','upstream_per_request_fee_usd')})
    q=q.model_copy(update=changes)
    job=type(settings.context.job).model_validate(settings.context.job.model_dump(mode='python')|{'pricing':q})
    x=type(settings.context).model_validate(settings.context.model_dump(mode='python')|{'job':job,
        'pricing_quote_hash':digest(q.model_dump(mode='json'))})
    xh=write(Path(settings.config.context.path),x)
    body=dict(model=q.model,route='byok' if q.is_byok else 'shared-only',account=q.account,
        key_fingerprint=q.key_fingerprint,ledger_registry_hash=q.ledger_registry_hash,terms_hash=q.terms_hash,
        provider_evidence_sha256='7'*64,valid_from=q.valid_from,expires_at=q.expires_at,
        **{key:getattr(q,key) for key in ('upstream_input_per_million_usd','upstream_output_per_million_usd',
            'upstream_per_image_fee_usd','upstream_per_request_fee_usd')})
    body.update(bounds_update or {})
    b=m.RawBillingBoundsV1.model_validate(body)
    raw=canonical_bytes(b.model_dump(mode='json'))
    if raw_transform:raw=raw_transform(raw)
    path=tmp_path/'observed-billing.json';path.write_bytes(raw);path.chmod(0o600)
    pointer=m.RawPrivateFileV1(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
    c=type(settings.config).model_validate(settings.config.model_dump(mode='python')|{'billing_bounds':pointer,
        'context':m.RawPrivateFileV1(path=settings.config.context.path,sha256=xh)})
    ch=write(settings.config_path,c);app=appointment(c,ch);ah=write(settings.appointment_path,app)
    return replace(settings,config=c,config_sha256=ch,appointment=app,appointment_sha256=ah,context=x),reads,state,b


def test_billing_pointer_absent_preserves_legacy_window_and_refuses_only_new_read(observed_exchange,tmp_path,monkeypatch):
    consumer,state,_=observed_exchange;settings,reads=configured_window_settings(consumer,tmp_path,monkeypatch)
    from dataclasses import replace
    assert settings.config.billing_bounds is None
    # Genuine old protected bytes omit the new field, including its null value.
    body=settings.config.model_dump(mode='json');del body['billing_bounds']
    raw=canonical_bytes(body);settings.config_path.write_bytes(raw)
    ch=hashlib.sha256(raw).hexdigest();app=appointment(settings.config,ch)
    ah=write(settings.appointment_path,app)
    settings=replace(settings,config_sha256=ch,appointment=app,appointment_sha256=ah)
    assert type(settings.current_window()) is m.RawOriginalAuthorityWindowV1
    before=(len(reads),len(state['requests']))
    with pytest.raises(PermissionError,match='billing pointer'):settings.read_billing_bounds()
    assert (len(reads),len(state['requests']))==before


def test_protected_billing_read_returns_exact_immutable_separately_named_commitments_without_io(observed_exchange,tmp_path,monkeypatch):
    from dataclasses import FrozenInstanceError,replace
    settings,reads,state,b=billing_settings(observed_exchange,tmp_path,monkeypatch)
    result=settings.read_billing_bounds();raw=Path(settings.config.billing_bounds.path).read_bytes()
    assert result.raw_bytes==raw and result.bounds==b
    assert result.original_file_sha256==settings.config.billing_bounds.sha256==hashlib.sha256(raw).hexdigest()
    assert result.canonical_record_sha256==digest(b.model_dump(mode='json'))
    assert reads==[] and state['requests']==[]  # No SQL, observer, metadata, allowance or paid send.
    with pytest.raises(FrozenInstanceError):result.raw_bytes=b'{}'
    with pytest.raises(ValueError):result.bounds.route='shared-only'
    for changes in ({'raw_bytes':bytearray(raw)},{'raw_bytes':raw+b' '},{'bounds':object()},
        {'original_file_sha256':'0'*64},{'canonical_record_sha256':'0'*64},
        {'bounds':b.model_copy(update={'provider_evidence_sha256':'0'*64})}):
        with pytest.raises((PermissionError,ValueError)):replace(result,**changes)
    for kwargs in ({'bounds':b},{'expected_sha256':result.original_file_sha256},{'route':'byok'}):
        with pytest.raises(TypeError):settings.read_billing_bounds(**kwargs)


@pytest.mark.parametrize('shape',['whitespace','order','missing_default','unknown','duplicate','numeric_decimal',
    'negative','nonfinite','bool_version','float_version','string_version','wrong_route','missing_route','missing_upstream','naive_date'])
def test_billing_full_canonical_model_bytes_no_duplicate_coercion_or_missing_dimension(observed_exchange,tmp_path,monkeypatch,shape):
    import json
    def transform(raw):
        value=json.loads(raw)
        if shape=='whitespace':return raw+b'\n'
        if shape=='order':return json.dumps(dict(reversed(tuple(value.items()))),separators=(',',':')).encode()
        if shape=='missing_default':del value['schema_version']
        elif shape=='unknown':value['approved']=True
        elif shape=='duplicate':return raw[:-1]+b',"model":"openai/gpt-6.1-sol"}'
        elif shape=='numeric_decimal':value['upstream_input_per_million_usd']=3
        elif shape=='negative':value['upstream_input_per_million_usd']='-1'
        elif shape=='nonfinite':return raw.replace(b'"upstream_input_per_million_usd":"3"',b'"upstream_input_per_million_usd":NaN')
        elif shape=='bool_version':value['schema_version']=True
        elif shape=='float_version':value['schema_version']=1.0
        elif shape=='string_version':value['schema_version']='1'
        elif shape=='wrong_route':value['route']='unknown'
        elif shape=='missing_route':del value['route']
        elif shape=='missing_upstream':del value['upstream_per_request_fee_usd']
        elif shape=='naive_date':value['valid_from']='2026-10-21T00:00:00'
        return canonical_bytes(value)
    settings,reads,state,_=billing_settings(observed_exchange,tmp_path,monkeypatch,raw_transform=transform)
    with pytest.raises((PermissionError,ValueError)):settings.read_billing_bounds()
    assert reads==[] and state['requests']==[]


@pytest.mark.parametrize('field',['account','key_fingerprint','ledger_registry_hash','terms_hash','model','route',
    'upstream_input_per_million_usd','upstream_output_per_million_usd','upstream_per_image_fee_usd',
    'upstream_per_request_fee_usd','expired','future','too_short'])
def test_billing_canonical_bound_but_wrong_current_quote_context_refuses(observed_exchange,tmp_path,monkeypatch,field):
    from decimal import Decimal
    def transform(raw):
        import json
        b=json.loads(raw)
        if field in {'account','key_fingerprint'}:b.update(account='key-sha256:'+'0'*64,key_fingerprint='0'*64)
        elif field=='model':b[field]='openai/gpt-6-astra'
        elif field=='route':
            b[field]='shared-only'
            for k in tuple(b):
                if k.startswith('upstream_'):b[k]='0'
        elif field.startswith('upstream_'):b[field]=str(Decimal(b[field])+1)
        elif field=='expired':b['valid_from']='2020-01-01T00:00:00Z';b['expires_at']='2020-01-02T00:00:00Z'
        elif field=='future':b['valid_from']='2099-01-01T00:00:00Z';b['expires_at']='2099-01-02T00:00:00Z'
        elif field=='too_short':
            b['expires_at']=(datetime.fromisoformat(b['expires_at'].replace('Z','+00:00'))-timedelta(seconds=1)).isoformat().replace('+00:00','Z')
        else:b[field]='0'*64
        # Canonical *typed* bytes prove refusal is bindings/windows, not spelling.
        return canonical_bytes(m.RawBillingBoundsV1.model_validate_json(canonical_bytes(b)).model_dump(mode='json'))
    settings,reads,state,_=billing_settings(observed_exchange,tmp_path,monkeypatch,raw_transform=transform)
    with pytest.raises(PermissionError):settings.read_billing_bounds()
    assert reads==[] and state['requests']==[]


@pytest.mark.parametrize('damage',['file_bytes','mode','hardlink','symlink','directory','oversize','relative','tuple_hash','tuple_path','issuer','job'])
def test_billing_file_or_appointed_tuple_tampering_before_read_refuses(observed_exchange,tmp_path,monkeypatch,damage):
    from dataclasses import replace
    settings,reads,state,_=billing_settings(observed_exchange,tmp_path,monkeypatch)
    pointer=settings.config.billing_bounds;path=Path(pointer.path)
    if damage=='file_bytes':path.write_bytes(path.read_bytes()+b' ')
    elif damage=='mode':path.chmod(0o644)
    elif damage=='hardlink':os.link(path,tmp_path/'second-link')
    elif damage=='symlink':
        saved=tmp_path/'billing-real';path.rename(saved);path.symlink_to(saved)
    elif damage=='directory':path.unlink();path.mkdir()
    elif damage=='oversize':path.write_bytes(b' '*100001)
    elif damage in {'relative','tuple_hash','tuple_path'}:
        changed=pointer.model_copy(update={'sha256':'0'*64} if damage=='tuple_hash' else
            {'path':'relative.json' if damage=='relative' else str(tmp_path/'foreign.json')})
        settings=replace(settings,config=settings.config.model_copy(update={'billing_bounds':changed}))
    elif damage=='issuer':settings=replace(settings,appointment=settings.appointment.model_copy(update={'issuer_actor':uuid4()}))
    else:settings=replace(settings,context=settings.context.model_copy(update={'job':settings.context.job.model_copy(update={'register_hash':'0'*64})}))
    with pytest.raises((PermissionError,ValueError,OSError)):settings.read_billing_bounds()
    assert reads==[] and state['requests']==[]


@pytest.mark.parametrize('damage',['billing_bytes','context_bytes','config_bytes','appointment_bytes','loaded_pointer'])
def test_billing_second_boundary_refuses_drift_before_return(observed_exchange,tmp_path,monkeypatch,damage):
    settings,reads,state,_=billing_settings(observed_exchange,tmp_path,monkeypatch)
    original=m.RawOriginalProviderSettingsV1._current_settings_pins;calls=[]
    def boundary(self):
        calls.append(1)
        if len(calls)==2:
            if damage=='loaded_pointer':
                object.__setattr__(self.config,'billing_bounds',self.config.billing_bounds.model_copy(update={'sha256':'0'*64}))
            else:
                path=(Path(self.config.billing_bounds.path) if damage=='billing_bytes' else
                    Path(self.config.context.path) if damage=='context_bytes' else
                    self.config_path if damage=='config_bytes' else self.appointment_path)
                path.write_bytes(path.read_bytes()+b' ')
        return original(self)
    monkeypatch.setattr(m.RawOriginalProviderSettingsV1,'_current_settings_pins',boundary)
    with pytest.raises(PermissionError):settings.read_billing_bounds()
    assert len(calls)==2 and reads==[] and state['requests']==[]


def test_billing_explicit_shared_only_zero_bounds_remain_distinct_from_missing_route(observed_exchange,tmp_path,monkeypatch):
    settings,reads,state,_=billing_settings(observed_exchange,tmp_path,monkeypatch,shared_only=True)
    result=settings.read_billing_bounds()
    assert result.bounds.route=='shared-only' and settings.context.job.pricing.is_byok is False
    assert all(getattr(result.bounds,key)==0 for key in ('upstream_input_per_million_usd',
        'upstream_output_per_million_usd','upstream_per_image_fee_usd','upstream_per_request_fee_usd'))
    assert reads==[] and state['requests']==[]


def test_billing_current_quote_cannot_expire_between_read_and_return(observed_exchange,tmp_path,monkeypatch):
    settings,reads,state,_=billing_settings(observed_exchange,tmp_path,monkeypatch)
    original=m.RawOriginalProviderSettingsV1._current_settings_pins;calls=[]
    def boundary(self):
        calls.append(1)
        result=original(self)
        if len(calls)==2:
            monkeypatch.setattr(m,'datetime',SimpleNamespace(now=lambda _:self.context.job.pricing.expires_at))
        return result
    monkeypatch.setattr(m.RawOriginalProviderSettingsV1,'_current_settings_pins',boundary)
    with pytest.raises(PermissionError):settings.read_billing_bounds()
    assert len(calls)==2 and reads==[] and state['requests']==[]
