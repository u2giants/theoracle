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
