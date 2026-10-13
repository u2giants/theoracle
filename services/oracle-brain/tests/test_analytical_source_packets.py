"""Mandatory W04/W07/W08/W10 invented packet boundary tests.

Reuse the source-owned suites; no supplier archive/download or live grant.
"""
from pathlib import Path
import runpy
ROOT=Path(__file__).resolve().parents[3]
TestAnalyticalInventory=runpy.run_path(str(ROOT/'scripts/oracle2/test_validate_analytical_packet.py'))['AnalyticalPacketTests']
TestAnalyticalDelivery=runpy.run_path(str(ROOT/'scripts/oracle2/test_analytical_source_packets.py'))['Packets']

def test_mandatory_inventory_cannot_silently_omit_packet_boundaries():
    inventory=runpy.run_path(str(ROOT/'scripts/oracle2/verify_workflow_integrity.py'))
    for stage in ('W04','W07','W08','W10','all'):
        assert 'analytical_source_packets' in inventory['required_suites'](stage)

def test_public_inventory_and_denied_flags_remain_intact():
    tests=runpy.run_path(str(ROOT/'scripts/oracle2/test_validate_analytical_packet.py'))
    tests['check_complete_public_inventory_never_confers_delivery_or_product_admission']()
