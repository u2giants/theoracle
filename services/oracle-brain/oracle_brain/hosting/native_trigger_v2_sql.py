"""Closed v2 SQL population: fixed files and seven fixed identifiers only.

No existing SQL file, role, database or authority is modified by compilation.
Installation is a separate exact-target action, never performed by this module.
"""
import re
from pathlib import Path
from types import MappingProxyType
from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY as I
from .synthetic_fixture import NATIVE_TRIGGER_V2_SCENARIO,fixed_scenario
from .synthetic_seed import compile_seed

MIGRATIONS=('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql',
 '006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql',
 '008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql','010_hosting_job_permissions.sql')
ROLE_MAP=MappingProxyType({
 'oracle2_gateway_metadata':I['groups']['gateway'],
 'oracle2_source_reader':I['groups']['reader'],
 'oracle2_candidate_compiler':I['groups']['compiler'],
 'oracle2_documentary_executor':I['groups']['executor'],
 'oracle_synthetic_gateway':I['gateway'],
 'oracle_synthetic_executor':I['executor'],
 'oracle_synthetic_projector':I['projector']})
_SQL=Path(__file__).resolve().parents[2]/'sql'
_PATTERN=re.compile(r'(?<![A-Za-z0-9_])('+ '|'.join(map(re.escape,ROLE_MAP))+r')(?![A-Za-z0-9_])')
_EXPECTED={
 'oracle2_gateway_metadata':'oracle_native_v2_gateway_metadata',
 'oracle2_source_reader':'oracle_native_v2_source_reader',
 'oracle2_candidate_compiler':'oracle_native_v2_candidate_compiler',
 'oracle2_documentary_executor':'oracle_native_v2_documentary_executor',
 'oracle_synthetic_gateway':'oracle_native_v2_gateway',
 'oracle_synthetic_executor':'oracle_native_v2_executor',
 'oracle_synthetic_projector':'oracle_native_v2_projector'}

def _require(value):
 if not value:raise PermissionError('fixed seven-role v2 SQL population required')

def _rewrite(text):
 _require(dict(ROLE_MAP)==_EXPECTED and len(set(ROLE_MAP.values()))==7)
 result=_PATTERN.sub(lambda m:ROLE_MAP[m.group()],text)
 _require(not _PATTERN.search(result))
 return result

def compile_v2_migration(name):
 _require(type(name) is str and name in MIGRATIONS)
 return _rewrite((_SQL/name).read_text()).encode()

def compile_v2_seed(parameters):
 scenario=fixed_scenario(NATIVE_TRIGGER_V2_SCENARIO)
 _require(parameters.get('synthetic_scenario')==NATIVE_TRIGGER_V2_SCENARIO
   and parameters.get('synthetic_scenario_seal')==scenario.seal())
 seed,manifest,payload,release=compile_seed(parameters)
 # Check the aggregate population, not each file: foundations contain no roles,
 # and the three LOGIN names are supplied by this exact fixed seed only.
 originals='\n'.join((_SQL/name).read_text() for name in MIGRATIONS)+'\n'+seed
 _require(set(_PATTERN.findall(originals))==set(ROLE_MAP))
 _require(seed.count('invented amber parcel')==1)
 result=_rewrite(seed).replace('invented amber parcel','invented silver envelope')
 return result,manifest,payload,release
