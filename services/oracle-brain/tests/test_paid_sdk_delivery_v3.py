"""Protected hosting constructor refusals; actual native positive lives in journey fixture."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from oracle_brain.hosting.paid_sdk_delivery_v3 import load_paid_sdk_bundle_v3,CurrentPaidSDKGuardV3


def test_paid_sdk_delivery_refuses_foreign_settings_and_unappointed_guard():
    for foreign in (None,True,object(),SimpleNamespace()):
        with pytest.raises(Exception,match='exact protected compiler SDK consume required'):
            load_paid_sdk_bundle_v3(foreign,foreign,artifact_id=uuid4(),artifact_version=1,embedding_dispatch_id=uuid4())
        with pytest.raises(Exception,match='actual compiler read guard required'):
            CurrentPaidSDKGuardV3(foreign)


def test_paid_sdk_guard_refuses_full_compile_guard_and_subclasses():
    from oracle_brain.hosting.purpose_journey_v2 import _PurposeCompilerReadGuardV3,_PurposeQualifiedReadGuardV3
    class ForeignQualified(_PurposeQualifiedReadGuardV3):pass
    for kind in (_PurposeCompilerReadGuardV3,ForeignQualified):
        with pytest.raises(PermissionError,match='actual compiler read guard required'):
            CurrentPaidSDKGuardV3(object.__new__(kind))
