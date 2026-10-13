import math
from collections import defaultdict
from decimal import Decimal
from statistics import median
from .event_contracts import LogReceipt

def measured_metrics(log: LogReceipt, explicit_exclusions: frozenset[str] = frozenset()):
    by_case=defaultdict(list)
    for e in log.events: by_case[e.case_id].append(e)
    completed=[c for c in by_case if c not in log.case_censoring and all(e.status=='completed' for e in by_case[c])]
    excluded=sorted(set(by_case) & set(explicit_exclusions)); retained=[c for c in completed if c not in explicit_exclusions]
    elapsed=[]; work={}; repeats={}; variants={}; provenance={}
    for case in sorted(by_case):
        es=sorted(by_case[case], key=lambda e:(e.timestamp,e.tie_order if e.tie_order is not None else 0))
        provenance[case]=[e.event_id for e in es]
        if case in retained:
            elapsed.append((max(e.timestamp for e in es)-min(e.timestamp for e in es)).total_seconds())
            starts=defaultdict(list); ends=defaultdict(list)
            for e in es:
                if e.lifecycle=='start': starts[e.activity_id].append(e)
                elif e.lifecycle=='complete': ends[e.activity_id].append(e)
            work[case]={a:(ends[a][0].timestamp-starts[a][0].timestamp).total_seconds() if len(starts[a])==len(ends[a])==1 and ends[a][0].timestamp>=starts[a][0].timestamp else None for a in set(starts)|set(ends)}
            counts=defaultdict(int)
            for e in es:
                if e.lifecycle in {'complete','point'}: counts[e.activity_id]+=1
            repeats[case]={a:n-1 for a,n in counts.items() if n>1}
            groups=defaultdict(list)
            for e in es: groups[e.timestamp].append(e)
            variants[case]='unordered' if any(len(g)>1 and (any(x.tie_order is None for x in g) or len({x.tie_order for x in g})!=len(g)) for g in groups.values()) else 'ordered'
    p90=sorted(elapsed)[math.ceil(.9*len(elapsed))-1] if elapsed else None
    costs=[e.cost for c in retained for e in by_case[c] if e.cost is not None]
    return {'source_import_id':str(log.import_id),'input_hash':log.input_hash,'mapping_hash':log.mapping_hash,'window':{'start':log.window_start.isoformat(),'end':log.window_end.isoformat()},'cases':{'total':len(by_case),'completed':len(completed),'retained_completed':len(retained),'excluded':len(excluded),'censored':len(set(by_case)-set(completed))},'elapsed_seconds':{'median':str(median(elapsed)) if elapsed else None,'p90_nearest_rank':str(p90) if p90 is not None else None,'values':elapsed},'worktime_seconds':work,'repeat_counts':repeats,'variants':variants,'observed_activity_paths':{c:[e.activity_id for e in sorted(by_case[c],key=lambda e:(e.timestamp,e.tie_order if e.tie_order is not None else 0))] if variants[c]=='ordered' else None for c in retained},'cost':str(sum(costs)) if costs else None,'cost_unit':'unspecified','event_ids':provenance,'method_version':'elapsed-wallclock-v1; p90-nearest-rank; no-causal-claims','quality_notes':list(log.quality_notes),'quarantined_row_count':len(log.quarantined_rows),'case_censoring':log.case_censoring}
