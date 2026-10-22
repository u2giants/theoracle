"""Uninstalled fixed legacy controller. No company grant, cutover or retry.

Actual source technical permission and canonical intake/viewer retain separate
owners. A complete finite snapshot is re-observed before intent/effect and
again after custody; no SQL socket spans other-plane/private byte work.
"""
from datetime import datetime, timezone
import hashlib
from uuid import UUID, uuid5

from oracle_brain.operating_model.contracts import canonical_bytes, digest
from oracle_brain.operating_model.protected_inputs_v1 import parse_canonical_object_v1
from oracle_brain.migration.migration_authority_v1 import MigrationAuthorityV1, MigrationOutcomeUnknown
from oracle_brain.migration.legacy_export_reader_v1 import TechnicalLegacyExportReaderV1, stable_inventory_entries_v1
from .original_intake_v1 import OriginalIntakeFactoryV1
from .original_view_v1 import OriginalViewerFactoryV1


class MigrationIntakeUnknown(MigrationOutcomeUnknown):
    """Immutable intent exists; no executable instruction or resend permission."""
    def __init__(self, intent_id):
        self.intent_id = intent_id
        super().__init__('Migration intake outcome unknown; observe own exact intent; never resend')


class LegacyMigrationFactoryV1:
    def __init__(self, *, register, prepare, observe, read, reconcile, citation, source, intake, viewer=None):
        consumers = (register, prepare, observe, read, reconcile, citation)
        operations = ('snapshot-register','batch-prepare','batch-observe','read','reconcile','citation-read')
        if (any(type(x) is not MigrationAuthorityV1 for x in consumers)
                or tuple(x.settings.config.operation for x in consumers) != operations
                or type(source) is not TechnicalLegacyExportReaderV1 or source.authority is not register
                or type(intake) is not OriginalIntakeFactoryV1 or viewer is not None and type(viewer) is not OriginalViewerFactoryV1):
            raise TypeError('fixed separate actual migration/source/intake/viewer consumers required')
        identity = ('principal_id','workspace_id','origin_system','descriptor_sha256','source_scope_sha256',
                    'source_program_sha256','intake_principal_id','intake_config_sha256')
        c = register.settings.config
        if (any(tuple(getattr(x.settings.config,k) for k in identity) != tuple(getattr(c,k) for k in identity) for x in consumers)
                or len({x.settings.config.session_role for x in consumers}) != len(consumers)
                or (intake.settings.config.principal_id,intake.settings.config.workspace_id,intake.settings.config_sha256) !=
                   (c.intake_principal_id,c.workspace_id,c.intake_config_sha256)
                or viewer is not None and (viewer.settings.config.principal_id,viewer.settings.config.workspace_id) != (c.principal_id,c.workspace_id)
                or intake.settings.config.expected_session_role in {x.settings.config.session_role for x in consumers}
                or viewer is not None and viewer.settings.config.expected_session_role in {x.settings.config.session_role for x in consumers}
                or viewer is not None and intake.settings.config.expected_session_role == viewer.settings.config.expected_session_role):
            raise PermissionError('separate independently appointed same-context consumers required')
        if source.document_capture is not None:
            selected=source.document_capture.profile
            if any(getattr(selected,k)!=getattr(intake.settings.config,k) for k in
                   ('storage_root','storage_device','storage_inode','storage_uid')):
                raise PermissionError('same independently pinned private capture/intake custody required')
        self.register,self.prepare,self.observe,self.reader,self.receipt,self.citation=consumers
        self.source,self.intake,self.viewer=source,intake,viewer

    def _time(self, deadline):
        for consumer in (self.register,self.prepare,self.observe,self.reader,self.receipt,self.citation):
            consumer._time(deadline)
        self.source._time(deadline)
        bound=self.intake.settings.current()
        if self.viewer is not None:
            bound=min(bound,self.viewer.settings.current())
        if deadline > bound:
            raise PermissionError('original controller window exceeds independent consumer horizon')

    def _snapshot_for_inventory(self, inventory_id, deadline):
        self._time(deadline)
        before=self.reader.status_v1(inventory_id,caller_deadline=deadline)
        snapshot=self.source.snapshot_v1(caller_deadline=deadline)
        inventory=parse_canonical_object_v1(snapshot.inventory_bytes,limit=64*1024*1024)
        after=self.reader.status_v1(inventory_id,caller_deadline=deadline)
        if (before['inventory_entries_sha256'] != digest(stable_inventory_entries_v1(inventory['entries']))
                or after['inventory_entries_sha256'] != before['inventory_entries_sha256']
                or after['revision'] != before['revision']):
            raise PermissionError('current full finite source population differs; new snapshot required')
        self._time(deadline)
        return snapshot,after

    @staticmethod
    def _control(result, operation):
        # No original body, path, permission receipt or executable instruction.
        allowed=('schema_version','inventory_id','event_id','sequence','kind','recorded_at','revision',
            'read_sequence','applied_sequence','counts','state','valid_until','redacted','original_operation_valid_until',
            'original_operation_window_unexpired','receipt_read_only','observation_only','write_authorized','resend_authorized')
        value={k:result[k] for k in allowed if k in result}
        value.update(operation=operation,qualification=False,source_read_authorized=False,viewer_authorized=False,
            dispatch_authorized=False,consistent_boundary_proven=False,serving_switch_authorized=False,
            shadow_comparison_accepted=False,company_acceptance=False)
        return value

    def register_snapshot_v1(self, command_id, *, caller_deadline):
        self._time(caller_deadline)
        snapshot=self.source.snapshot_v1(caller_deadline=caller_deadline)
        body=parse_canonical_object_v1(snapshot.inventory_bytes,limit=64*1024*1024)
        result=self.register.register_v1(snapshot.inventory_bytes,command_id,self.receipt,caller_deadline=caller_deadline)
        try:
            if result.get('inventory_id') != body['inventory_id']:
                raise PermissionError('registered inventory identity differs')
            self._time(caller_deadline)
            return self._control(result,'snapshot-registration')
        except Exception:
            raise MigrationOutcomeUnknown('Registered inventory outcome unknown; reconcile exact command; never resend') from None

    def import_batch_v1(self, inventory_id, expected_head, command_id, *, caller_deadline):
        snapshot,status=self._snapshot_for_inventory(inventory_id,caller_deadline)
        if status['revision'] != expected_head:
            raise PermissionError('actual current inventory revision differs')
        result=self.prepare.prepare_v1(inventory_id,expected_head,command_id,self.receipt,caller_deadline=caller_deadline)
        try:
            if result.get('inventory_id') != str(inventory_id):
                raise PermissionError('prepared inventory identity differs')
            return self._import_prepared_batch_v1(inventory_id, command_id, result, caller_deadline)
        except MigrationOutcomeUnknown:
            raise
        except Exception:
            raise MigrationOutcomeUnknown('Prepared batch outcome unknown; reconcile exact command; never resend') from None

    def _import_prepared_batch_v1(self, inventory_id, command_id, result, caller_deadline):
        instructions=result.get('intake_instructions',[])
        observations=result.get('observation_instructions',[])
        if (type(instructions) is not list or type(observations) is not list
                or len(instructions)+len(observations)>100):
            raise MigrationOutcomeUnknown('Prepared instruction set unknown; no intake dispatched')
        if result.get('state') == 'UNKNOWN':
            return self._control(result,'batch-UNKNOWN')
        for instruction in instructions:
            fields={'intent_id','legacy_id','metadata_sha256','source_id','expected_head','idempotency_key',
                'original_sha256','byte_count','original_dispatch_deadline','legacy_kind','media_type'}
            if type(instruction) is not dict or set(instruction)!=fields:
                raise MigrationOutcomeUnknown('Prepared instruction schema unknown; no retry')
            intent=UUID(instruction['intent_id'])
            # A fresh complete source pass precedes EVERY possible intake.
            current,_=self._snapshot_for_inventory(inventory_id,caller_deadline)
            pair=(instruction['legacy_kind'],instruction['media_type'])
            if pair==('message','text/plain'):
                population=current.messages
            elif pair==('document','application/pdf'):
                population=current.documents
            else:
                raise MigrationIntakeUnknown(intent)
            matches=[m for m in population if str(m.legacy_id)==instruction['legacy_id']]
            if len(matches)!=1:
                raise MigrationIntakeUnknown(intent)
            message=matches[0]
            if ((message.metadata_sha256,message.original_sha256,message.byte_count) !=
                    (instruction['metadata_sha256'],instruction['original_sha256'],instruction['byte_count'])
                    or hashlib.sha256(message.data).hexdigest()!=message.original_sha256):
                raise MigrationIntakeUnknown(intent)
            original_deadline=datetime.fromisoformat(instruction['original_dispatch_deadline'])
            if original_deadline > caller_deadline or datetime.now(timezone.utc)>=original_deadline:
                raise MigrationIntakeUnknown(intent)
            self._time(original_deadline)
            try:
                # Canonical014 alone allocates first UUID from NULL/head0.
                kwargs=dict(source_id=UUID(instruction['source_id']) if instruction['source_id'] else None,
                    expected_head=instruction['expected_head'],idempotency_key=UUID(instruction['idempotency_key']),
                    original_sha256=message.original_sha256,data=message.data,caller_deadline=original_deadline)
                if pair==('message','text/plain'):
                    self.intake.intake_text_v1(filename='legacy_'+instruction['legacy_id']+'.txt',**kwargs)
                else:
                    self.intake.intake_pdf_v1(filename='legacy_'+instruction['legacy_id']+'.pdf',**kwargs)
                # Never label late/source-revoked custody as active import.
                self._snapshot_for_inventory(inventory_id,original_deadline)
            except Exception:
                # Immutable global intent already fences all restarts/reinstalls.
                # Do not issue a second intake, new key, role, deadline or grant.
                raise MigrationIntakeUnknown(intent) from None
            observed=self.observe.observe_v1(intent,self.intake.settings.config_sha256,
                uuid5(command_id,'observe:'+str(intent)),self.receipt,caller_deadline=original_deadline)
            if observed.get('state') not in ('custody-observed','metadata-only'):
                raise MigrationIntakeUnknown(intent)
        for raw_intent in observations:
            # Permission/metadata-only changes retain existing bytes/sourceUUID.
            self._snapshot_for_inventory(inventory_id,caller_deadline)
            self.observe.observe_v1(UUID(raw_intent),self.intake.settings.config_sha256,
                uuid5(command_id,'observe:'+raw_intent),self.receipt,caller_deadline=caller_deadline)
        self._snapshot_for_inventory(inventory_id,caller_deadline)
        return self._control(self.reader.status_v1(inventory_id,caller_deadline=caller_deadline),'batch-control')

    def observe_intent_v1(self, intent_id, command_id, *, caller_deadline):
        # Explicit CURRENT metadata action after uncertain/expired dispatch.
        # It never calls intake or changes the immutable dispatch deadline.
        self.observe._time(caller_deadline)
        self.receipt._time(caller_deadline)
        result=self.observe.observe_v1(intent_id,self.observe.settings.config.intake_config_sha256,command_id,
            self.receipt,caller_deadline=caller_deadline)
        try:
            self.observe._time(caller_deadline)
            self.receipt._time(caller_deadline)
            return self._control(result,'observation-only')
        except Exception:
            raise MigrationOutcomeUnknown('Observation outcome unknown; reconcile exact command; never resend') from None

    def reconcile_v1(self, command_id, *, caller_deadline):
        # Current independent forensic authority may outlive original write.
        result=self.receipt.reconcile_v1(command_id,caller_deadline=caller_deadline)
        return self._control(result,'receipt-read-only')

    def resolve_citation_v1(self, inventory_id, legacy_citation_id, *, caller_deadline):
        if self.viewer is None:
            raise PermissionError('independent original viewer unavailable; citation withheld')
        self._time(caller_deadline)
        before=self.citation.citation_metadata_v1(inventory_id,legacy_citation_id,caller_deadline=caller_deadline)
        if before.get('redacted') is not False:
            raise PermissionError('current original citation unavailable')
        source,revision=UUID(before['source_id']),before['revision']
        viewed=self.viewer.read_original_v1(source,revision,caller_deadline=caller_deadline)
        # Actual independent viewer has closed both SQL sockets and verified its
        # separately pinned custody. No source bytes are returned by controller.
        after=self.citation.citation_metadata_v1(inventory_id,legacy_citation_id,caller_deadline=caller_deadline)
        if any(before.get(k)!=after.get(k) for k in ('source_id','revision','original_sha256','redacted')):
            raise PermissionError('current citation changed after independent view')
        if hashlib.sha256(viewed.data).hexdigest()!=before['original_sha256']:
            raise PermissionError('actual independent original bytes differ')
        self._time(caller_deadline)
        return dict(schema_version=1,operation='current-citation',source_id=str(source),revision=revision,
            href=f'/consultant/replacement/originals/{source}/{revision}',
            independent_viewer_check_required=True,qualification=False,company_acceptance=False,
            consistent_boundary_proven=False,serving_switch_authorized=False,
            valid_until=min(viewed.valid_until,datetime.fromisoformat(after['valid_until']),caller_deadline).isoformat())
