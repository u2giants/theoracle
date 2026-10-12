"""Strict model suggestions; no provider retry, guessed identity, or policy promotion."""
import json
from ..model import BusinessOperatingModel
from ..assembly import validate_assembly
from ..observations import Observation
from ..coverage import CoverageRecord,validate_coverage


def admit_model_response(raw_response:str, *, observations:dict[str,Observation], obligations,
                         coverage_records, inventory_hash:str, object_evidence,
                         accepted_mapping_events:frozenset[str]=frozenset()):
    model=BusinessOperatingModel.model_validate_json(raw_response)
    validate_assembly(model,observations,accepted_mapping_events=accepted_mapping_events)
    validate_coverage(obligations,coverage_records,object_evidence=object_evidence,
                      independent_inventory_hash=inventory_hash)
    if any(w.status!='reported' for w in model.workflows):raise PermissionError('extraction cannot promote policy')
    return model
