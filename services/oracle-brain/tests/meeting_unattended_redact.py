"""§5 fixture-only redaction helpers for the S07 unattended packet.

Importable without the heavy meeting-test imports (no psycopg/fcntl) so
offline unit tests can prove the allow-list keeps the packet's fixed
hyphenated tokens and still redacts paths/hosts/secrets.
"""
import json,math,re
from pathlib import Path

# ---- §5 exhaustive allow-list for this packet. ----
_FIXED_REFUSAL_STRINGS=frozenset({
    'Installed Recall operation unavailable',
    'Replacement control unavailable',
    'fixed requester lifecycle/framing required',
    'original requester window expired or excessive',
    'original requester deadline elapsed',
    'original requester reply expired',
    'fixed bounded protected metadata required',
})
_STAGE_NAMES=frozenset({'prepare','claim','current','exchange','observe','wait'})
_WIRE_OPERATIONS=frozenset({'prepare','claim','current','observe','status'})
_EFFECT_NAMES=frozenset({'capture-create','capture-leave','capture-retrieve'})
_HEAD_STATE_NAMES=frozenset({'capture_status_unknown','open','closed','terminal_observed','inflight','observed','UNKNOWN','idle','prepared','claimed'})
# Pre-child step names exactly as test_meeting_unattended_sql.py assigns `step=`.
_PRE_CHILD_STEP_NAMES=frozenset({
    'start_unattended','install-wraps','queue-diagnostic','cycle-diagnostic',
    'warmup-queue-reads','refused-prepare-warmup','sql-zero-asserts',
    'child-spawn-ready','warmup-observations','child-wait','stdout-redact',
    'collect-diagnostics','returncode-assert','outcome-parse','repeated-claim',
    'post-create-current-queue','terminal-loop','terminal-asserts','unattended-outcome',
})
# Teardown step names exactly as the §7 _step() loop writes them.
_TEARDOWN_STEP_NAMES=frozenset({
    'supervision-scope','replay-spool-copy','selected-state','provider-routes',
    'observer-files','stack-close','jsonl-close-then-copy','owned-process-cleanup',
    'private-cleanup',
})
# claim/receipt stage domain from 020_meeting_capture.sql:664 (includes the
# literal '-' placeholder used by non-retrieve effects).
_CLAIM_STAGES=frozenset({'-','pre-stop-consistency','post-stop-terminal'})
# observation kinds from 020_meeting_capture.sql:806.
_OBSERVATION_KINDS=frozenset({'create-observed','leave-observed','metadata-observed'})
# Response-header keywords the create-worker wrap logs (_logged_send_header),
# including BaseHTTPRequestHandler's automatic Server/Date on send_response.
_HEADER_KEYWORDS=frozenset({
    'Content-Length','Cache-Control','Connection','Content-Type','Server','Date',
})
# Fixed header values the wrap logs from _protected_control_listener_v1.
_HEADER_VALUES=frozenset({'no-store','close','application/json'})
_ENUM_STRINGS=(_STAGE_NAMES|_WIRE_OPERATIONS|_EFFECT_NAMES|_HEAD_STATE_NAMES
    |_PRE_CHILD_STEP_NAMES|_TEARDOWN_STEP_NAMES|_CLAIM_STAGES|_OBSERVATION_KINDS
    |_HEADER_KEYWORDS|_HEADER_VALUES
    |{'true','false','null','REDACTED','unlisted','ok','enter','exit','error','wrap',
      'response','request','refused'})
_UUID_RE=re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_HEX64_RE=re.compile(r'^[0-9a-f]{64}$')
_ISO_RE=re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$')
_MODE_RE=re.compile(r'^0[0-7]{3}$')
_IDENT_RE=re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_COMPOUND_RE=re.compile(r'^[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*$')
_DIGITS_RE=re.compile(r'^\d+$')
_HTTP_DATE_RE=re.compile(r'^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$')
_SERVER_VERSION_RE=re.compile(r'^BaseHTTP/\d+\.\d+ Python/\d+\.\d+\.\d+$')
_WRAP_NAMES=frozenset({'settings.current','execute_v1','_parse','peer_der_v1','fixed_request_length_v1','read_request_body_v1','_request_fence_v1'})
_PATHY_RE=re.compile(r'(^|[^A-Za-z0-9_])(/tmp/|/home/|/proc/|[A-Za-z]:[\\/]|localhost(?!\.localdomain))')

def _value_allowed(v):
    if v is None or type(v) is bool:return True
    if type(v) is int:return True
    if type(v) is float:return math.isfinite(v)
    if type(v) is not str:return False
    if v in _ENUM_STRINGS or v in _FIXED_REFUSAL_STRINGS or v in _WRAP_NAMES or v=='localhost.localdomain':return True
    if _UUID_RE.match(v) or _HEX64_RE.match(v) or _ISO_RE.match(v) or _MODE_RE.match(v):return True
    if _DIGITS_RE.match(v) or _HTTP_DATE_RE.match(v) or _SERVER_VERSION_RE.match(v):return True
    if _IDENT_RE.match(v) or _COMPOUND_RE.match(v):
        return not _PATHY_RE.search(v)
    return False

def redact_record(record):
    """§5 deterministic deny rule for every JSON artifact and jsonl append.

    Walks every value. Anything not matched by the allow-list becomes
    "REDACTED" and the parallel key "<field>_kind": "unlisted" is set.
    List fields propagate the marker when any member is redacted.
    """
    def walk(node,key):
        if type(node) is dict:
            out={}
            for k,v in node.items():
                out[k],flag=walk(v,k)
                if flag:out[str(k)+'_kind']='unlisted'
            return out,False
        if type(node) is list:
            out=[];flagged=False
            for v in node:
                item,flag=walk(v,key)
                out.append(item)
                if flag:flagged=True
            return out,flagged
        if type(node) is bytes:return 'REDACTED',True
        if _value_allowed(node):return node,False
        return 'REDACTED',True
    out,_=walk(record,None)
    return out

def _write_json_artifact(path,record):
    """Every JSON artifact write goes through redact_record."""
    Path(path).write_text(json.dumps(redact_record(record),sort_keys=True,default=str))
